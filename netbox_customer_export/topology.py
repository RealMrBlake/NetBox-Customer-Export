"""Netzwerk-Topologie: Graph aus den Kabelverbindungen, Ebenen-Layout, PNG- und draw.io-Ausgabe."""
import base64
from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass, field
from io import BytesIO
from xml.sax.saxutils import escape, quoteattr

from .symbols import KINDS, SIZE, SymbolResolver, builtin_icon

MAX_PER_ROW = 8


@dataclass
class Node:
    id: str
    label: str
    kind: str
    icon: bytes
    sub: list = field(default_factory=list)
    external: bool = False  # Gerät eines anderen Standorts / Provider
    layer: int = 0
    x: float = 0
    y: float = 0


@dataclass
class Edge:
    a: str
    b: str
    labels: list = field(default_factory=list)


@dataclass
class Graph:
    title: str
    nodes: "OrderedDict[str, Node]"
    edges: list


# --- Graph aufbauen -----------------------------------------------------------

def _device_sub(device, details):
    sub = []
    if "model" in details:
        sub.append(str(device.device_type.model))
    if "primary_ip" in details and device.primary_ip:
        sub.append(str(device.primary_ip.address.ip))
    return sub


def build_graphs(scope, opts):
    """Ein Graph je Standort. Geräte anderer Standorte und Provider-Leitungen erscheinen als externe Knoten."""
    from dcim.models import Interface

    details = set(opts.get("topo_details") or [])
    resolver = SymbolResolver()
    devices = list(
        scope.devices().select_related(
            "role", "device_type__manufacturer", "site", "primary_ip4", "primary_ip6"
        ).order_by("site__name", "name")
    )
    drawn = {}  # device.pk -> (kind, icon)
    for d in devices:
        kind, icon = resolver.resolve(d)
        if kind:
            drawn[d.pk] = (kind, icon)
    by_pk = {d.pk: d for d in devices}

    # Verbindungen: vollständige Kabelpfade (auch über Patchpanels) zwischen Interfaces
    links = defaultdict(list)  # (a, b) -> ["Gi1/0/1 – eth0", …]
    external = {}  # node_id -> Node-Vorlage
    ifaces = scope.restrict(
        Interface.objects.filter(device_id__in=list(drawn), cable__isnull=False)
    ).select_related("device")
    for iface in ifaces:
        try:
            endpoints = iface.connected_endpoints or []
        except Exception:  # noqa: BLE001 – defekte Pfade überspringen
            continue
        for ep in endpoints:
            model = ep._meta.model_name
            a = f"d{iface.device_id}"
            if model == "interface":
                peer = ep.device
                if peer.pk == iface.device_id:
                    continue
                if peer.pk not in by_pk:  # Gerät außerhalb des Scopes
                    if not opts.get("topo_external"):
                        continue
                    kind, icon = resolver.resolve(peer)
                    if not kind:
                        continue
                    external[f"d{peer.pk}"] = Node(f"d{peer.pk}", peer.name or str(peer), kind, icon, [str(peer.site)], external=True)
                elif peer.pk not in drawn:
                    continue
                b, label = f"d{peer.pk}", f"{iface.name} – {ep.name}"
            elif model in ("circuittermination", "providernetwork"):
                if not opts.get("topo_external"):
                    continue
                circuit = getattr(ep, "circuit", None)
                b = f"c{circuit.pk}" if circuit else f"p{ep.pk}"
                title = str(circuit.provider) if circuit else str(ep)
                sub = [str(circuit.cid)] if circuit else []
                external[b] = Node(b, title, "cloud", builtin_icon("cloud"), sub, external=True)
                label = iface.name
            else:
                continue
            key = tuple(sorted((a, b)))
            # Beschriftung immer aus Sicht von key[0]; jedes Kabel wird von beiden Enden gefunden
            if key[0] != a:
                label = " – ".join(reversed(label.split(" – ")))
            if label not in links[key]:
                links[key].append(label)

    # Knoten je Standort
    graphs = []
    sites = OrderedDict()
    for pk in drawn:
        sites.setdefault(by_pk[pk].site, []).append(pk)
    for site, pks in sites.items():
        nodes = OrderedDict()
        for pk in pks:
            d = by_pk[pk]
            kind, icon = drawn[pk]
            nodes[f"d{pk}"] = Node(f"d{pk}", d.name or str(d), kind, icon, _device_sub(d, details))
        edges = []
        for (a, b), labels in links.items():
            in_a, in_b = a in nodes, b in nodes
            if not (in_a or in_b):
                continue
            for nid, inside in ((a, in_a), (b, in_b)):
                if not inside:
                    other = external.get(nid)
                    if other is None:  # Gerät eines anderen Standorts im selben Scope
                        d = by_pk[int(nid[1:])]
                        kind, icon = drawn[d.pk]
                        other = Node(nid, d.name or str(d), kind, icon, [str(d.site)], external=True)
                    nodes[nid] = Node(**{**other.__dict__})
            edges.append(Edge(a, b, labels))
        if not opts.get("topo_isolated"):
            linked = {n for e in edges for n in (e.a, e.b)}
            nodes = OrderedDict((k, v) for k, v in nodes.items() if k in linked)
        if nodes:
            _layout(nodes, edges)
            graphs.append(Graph(f"Standort {site}", nodes, edges))
    return graphs


# --- Layout -------------------------------------------------------------------

def _layout(nodes, edges):
    """Ebenen per Breitensuche ab den „höchsten“ Geräten (Provider, Firewall, Router …), dann Reihenfolge nach Nachbarn."""
    adj = defaultdict(set)
    for e in edges:
        adj[e.a].add(e.b)
        adj[e.b].add(e.a)
    tier = {nid: KINDS.get(n.kind, ("", 4))[1] for nid, n in nodes.items()}

    layer = {n: None for n in nodes if not adj[n]}  # isolierte Knoten: unterste Zeile
    remaining = set(nodes) - set(layer)
    while remaining:
        # jede Zusammenhangskomponente ab ihren am höchsten eingestuften Knoten
        top = min(tier[n] for n in remaining)
        roots = [n for n in nodes if n in remaining and tier[n] == top]
        queue = deque()
        for r in roots:
            layer[r] = tier[r] if tier[r] <= 1 else 0
            queue.append(r)
        while queue:
            cur = queue.popleft()
            remaining.discard(cur)
            for nb in adj[cur]:
                if nb not in layer:
                    layer[nb] = layer[cur] + 1  # Ebene folgt der Verkabelung
                    queue.append(nb)

    used = sorted({v for v in layer.values() if v is not None})
    rank = {v: i for i, v in enumerate(used)}
    bottom = len(used)
    rows = defaultdict(list)
    for nid in nodes:
        rows[rank[layer[nid]] if layer[nid] is not None else bottom].append(nid)

    # Reihenfolge: Schwerpunkt der Nachbarn in der Zeile darüber (reduziert Kreuzungen)
    pos = {}
    for r in sorted(rows):
        row = rows[r]
        if r > 0:
            def bary(n):
                ps = [pos[p] for p in adj[n] if p in pos]
                return sum(ps) / len(ps) if ps else 1e9
            row.sort(key=bary)
        for i, n in enumerate(row):
            pos[n] = i

    # Zeilen mit zu vielen Knoten umbrechen, dann Koordinaten
    CELL_W, CELL_H = 200, 190
    lines = []
    for r in sorted(rows):
        row = rows[r]
        for i in range(0, len(row), MAX_PER_ROW):
            lines.append(row[i : i + MAX_PER_ROW])
    width = max(len(line) for line in lines) * CELL_W
    for li, line in enumerate(lines):
        offset = (width - len(line) * CELL_W) / 2
        for i, nid in enumerate(line):
            nodes[nid].x = offset + i * CELL_W + CELL_W / 2
            nodes[nid].y = li * CELL_H + 70


def _oriented(graph, e):
    """Port-Beschriftungen aus Sicht des oberen Knotens („Uplink-Port – Downlink-Port“)."""
    a, b = graph.nodes[e.a], graph.nodes[e.b]
    if a.y <= b.y:
        return e.labels
    return [" – ".join(reversed(x.split(" – "))) for x in e.labels]


# --- PNG ----------------------------------------------------------------------

def _font(size, bold=False):
    from PIL import ImageFont

    names = ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf") if bold else ("DejaVuSans.ttf", "Arial.ttf", "arial.ttf")
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def render_png(graph, show_ports=False, scale=2):
    from PIL import Image, ImageDraw

    icon = 64
    nodes = graph.nodes.values()
    w = int((max(n.x for n in nodes) + 100) * scale)
    h = int((max(n.y for n in nodes) + 110) * scale)
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    f_name, f_sub, f_port = _font(12 * scale, bold=True), _font(10 * scale), _font(8 * scale)

    def c(n):
        return n.x * scale, n.y * scale

    def anchors(a, b):
        """Linie unterhalb der Beschriftung des oberen Knotens beginnen, oben am unteren Symbol enden."""
        if a.y > b.y:
            a, b = b, a
        if a.y == b.y:
            return c(a), c(b)
        label_h = 22 + 13 * len(a.sub)
        return (a.x * scale, (a.y + icon / 2 + label_h) * scale), (b.x * scale, (b.y - icon / 2 - 2) * scale)

    for e in graph.edges:
        a, b = graph.nodes[e.a], graph.nodes[e.b]
        dashed = a.external or b.external
        color = (150, 150, 150) if dashed else (60, 60, 60)
        (x1, y1), (x2, y2) = anchors(a, b)
        if dashed:
            steps = int(max(abs(x2 - x1), abs(y2 - y1)) / (8 * scale)) or 1
            for i in range(0, steps, 2):
                t1, t2 = i / steps, min((i + 1) / steps, 1)
                d.line([(x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1), (x1 + (x2 - x1) * t2, y1 + (y2 - y1) * t2)], fill=color, width=2 * scale)
        else:
            d.line([(x1, y1), (x2, y2)], fill=color, width=2 * scale)
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        text = None
        if show_ports:
            labels = _oriented(graph, e)
            text = labels[0] + (f" (+{len(labels) - 1})" if len(labels) > 1 else "")
        elif len(e.labels) > 1:
            text = f"{len(e.labels)}×"
        if text:
            tw = d.textlength(text, font=f_port)
            d.rounded_rectangle([mx - tw / 2 - 4 * scale, my - 7 * scale, mx + tw / 2 + 4 * scale, my + 7 * scale], radius=3 * scale, fill=(255, 255, 255), outline=(200, 200, 200))
            d.text((mx, my), text, fill=(40, 40, 40), font=f_port, anchor="mm")

    for n in nodes:
        x, y = c(n)
        pic = Image.open(BytesIO(n.icon)).convert("RGBA").resize((icon * scale, icon * scale), Image.LANCZOS)
        if n.external:
            alpha = pic.getchannel("A").point(lambda v: int(v * 0.55))
            pic.putalpha(alpha)
        img.paste(pic, (int(x - icon * scale / 2), int(y - icon * scale / 2)), pic)
        ty = y + icon * scale / 2 + 4 * scale
        d.text((x, ty), _clip(d, n.label, f_name, 190 * scale), fill=(110, 110, 110) if n.external else (20, 20, 20), font=f_name, anchor="ma")
        for i, line in enumerate(n.sub):
            d.text((x, ty + (16 + i * 13) * scale), _clip(d, line, f_sub, 190 * scale), fill=(100, 100, 100), font=f_sub, anchor="ma")

    out = BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def _clip(d, text, font, width):
    if d.textlength(text, font=font) <= width:
        return text
    while text and d.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text + "…"


# --- draw.io ------------------------------------------------------------------

def _small_icon(png, px=64):
    from PIL import Image

    img = Image.open(BytesIO(png)).convert("RGBA").resize((px, px), Image.LANCZOS)
    out = BytesIO()
    img.save(out, "PNG", optimize=True)
    return base64.b64encode(out.getvalue()).decode("ascii")


def render_drawio(graphs, show_ports=False):
    """draw.io-Datei (mxfile) mit einer Seite je Standort. Symbole als eingebettete Bilder."""
    icon_cache = {}
    pages = []
    for gi, g in enumerate(graphs):
        cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
        for n in g.nodes.values():
            key = id(n.icon)
            if key not in icon_cache:
                icon_cache[key] = _small_icon(n.icon)
            label = escape(n.label) + "".join(f"<br><font style=\"font-size:10px\" color=\"#666666\">{escape(s)}</font>" for s in n.sub)
            style = (
                "shape=image;html=1;verticalLabelPosition=bottom;verticalAlign=top;labelBackgroundColor=none;"
                f"imageAspect=0;aspect=fixed;fontStyle=1;{'opacity=55;' if n.external else ''}"
                f"image=data:image/png,{icon_cache[key]};"
            )
            cells.append(
                f'<mxCell id="{n.id}" value={quoteattr(label)} style={quoteattr(style)} vertex="1" parent="1">'
                f'<mxGeometry x="{n.x - 32:.0f}" y="{n.y - 32:.0f}" width="64" height="64" as="geometry"/></mxCell>'
            )
        for i, e in enumerate(g.edges):
            dashed = g.nodes[e.a].external or g.nodes[e.b].external
            label = "<br>".join(escape(x) for x in _oriented(g, e)) if show_ports else (f"{len(e.labels)}×" if len(e.labels) > 1 else "")
            style = f"endArrow=none;html=1;strokeWidth=2;strokeColor={'#999999' if dashed else '#333333'};{'dashed=1;' if dashed else ''}fontSize=9;labelBackgroundColor=#ffffff;"
            cells.append(
                f'<mxCell id="e{i}" value={quoteattr(label)} style={quoteattr(style)} edge="1" parent="1" source="{e.a}" target="{e.b}">'
                '<mxGeometry relative="1" as="geometry"/></mxCell>'
            )
        pages.append(
            f'<diagram id="page{gi}" name={quoteattr(g.title)}><mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" '
            f'guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="0" pageScale="1" math="0" shadow="0">'
            f'<root>{"".join(cells)}</root></mxGraphModel></diagram>'
        )
    return f'<mxfile host="netbox-customer-export">{"".join(pages)}</mxfile>'.encode("utf-8")


__all__ = ["build_graphs", "render_png", "render_drawio", "SIZE"]
