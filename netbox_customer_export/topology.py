"""Netzwerk-Topologie: Graph aus den Kabelverbindungen, Ebenen-Layout mit rechtwinkligen Leitungen, PNG-Ausgabe."""
from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass, field
from io import BytesIO

from .symbols import KINDS, SymbolResolver, builtin_icon

MAX_PER_ROW = 12  # breitere Zeilen werden umgebrochen


@dataclass
class Node:
    id: str
    label: str
    kind: str
    icon: bytes
    sub: list = field(default_factory=list)
    external: bool = False  # Gerät eines anderen Standorts / Provider
    row: int = 0  # Zeile im Diagramm (nach Umbruch)
    x: float = 0  # Mitte, in Layout-Pixeln
    y: float = 0  # Oberkante des Symbols, wird beim Zeichnen gesetzt


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

CELL_W = 190  # Spaltenbreite
ICON = 64  # Symbolgröße
LANE = 11  # Abstand der Sammelschienen im Zwischenraum
PORT_H = 13  # Zeilenhöhe der Port-Beschriftungen


def _label_h(n):
    return 20 + 13 * len(n.sub)


def _layout(nodes, edges):
    """Ebenen per Breitensuche ab den „höchsten“ Geräten (Provider, Firewall, Router …).

    Die Breitensuche garantiert, dass verbundene Geräte höchstens eine Ebene auseinanderliegen – so bleiben
    alle Leitungen kurz. Danach wird die Reihenfolge in mehreren Durchläufen (abwärts/aufwärts) nach dem
    Schwerpunkt der Nachbarn sortiert, um Kreuzungen zu minimieren.
    """
    adj = defaultdict(set)
    for e in edges:
        adj[e.a].add(e.b)
        adj[e.b].add(e.a)
    tier = {nid: KINDS.get(n.kind, ("", 4))[1] for nid, n in nodes.items()}

    layer = {n: None for n in nodes if not adj[n]}  # isolierte Knoten: unterste Zeile
    remaining = set(nodes) - set(layer)
    while remaining:
        top = min(tier[n] for n in remaining)
        queue = deque()
        for r in [n for n in nodes if n in remaining and tier[n] == top]:
            layer[r] = 0
            queue.append(r)
        while queue:
            cur = queue.popleft()
            remaining.discard(cur)
            for nb in adj[cur]:
                if nb not in layer:
                    layer[nb] = layer[cur] + 1
                    queue.append(nb)

    used = sorted({v for v in layer.values() if v is not None})
    rank = {v: i for i, v in enumerate(used)}
    order = defaultdict(list)
    for nid in nodes:
        order[rank[layer[nid]] if layer[nid] is not None else len(used)].append(nid)
    rows = sorted(order)

    def centered(r):
        row = order[r]
        return {n: i - (len(row) - 1) / 2 for i, n in enumerate(row)}

    def sweep(r, ref):
        if ref not in order:
            return
        pos, cur = centered(ref), centered(r)

        def key(n):
            ps = [pos[p] for p in adj[n] if p in pos]
            return sum(ps) / len(ps) if ps else cur[n]

        order[r].sort(key=key)

    for _ in range(4):
        for r in rows[1:]:
            sweep(r, r - 1)
        for r in reversed(rows[:-1]):
            sweep(r, r + 1)

    # Zeilen umbrechen und Spalten vergeben
    lines = []
    for r in rows:
        row = order[r]
        for i in range(0, len(row), MAX_PER_ROW):
            lines.append(row[i : i + MAX_PER_ROW])
    width = max(len(line) for line in lines) * CELL_W
    for li, line in enumerate(lines):
        offset = (width - len(line) * CELL_W) / 2
        for i, nid in enumerate(line):
            nodes[nid].row = li
            nodes[nid].x = offset + i * CELL_W + CELL_W / 2


def _oriented(graph, e):
    """Port-Beschriftungen aus Sicht des oberen (bzw. linken) Knotens: „Uplink-Port – Downlink-Port“."""
    a, b = graph.nodes[e.a], graph.nodes[e.b]
    if (a.row, a.x) <= (b.row, b.x):
        return e.labels
    return [" – ".join(reversed(x.split(" – "))) for x in e.labels]


def _edge_text(graph, e, show_ports):
    if show_ports:
        labels = _oriented(graph, e)
        return labels[0] + (f" (+{len(labels) - 1})" if len(labels) > 1 else "")
    return f"{len(e.labels)}×" if len(e.labels) > 1 else None


# --- PNG ----------------------------------------------------------------------

PALETTE = [
    (31, 119, 180), (214, 39, 40), (44, 160, 44), (148, 103, 189), (255, 127, 14),
    (23, 150, 170), (140, 86, 75), (188, 150, 20), (200, 80, 160), (90, 90, 90),
]
EXTERNAL = (160, 160, 160)


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


def _plan(graph, show_ports):
    """Ordnet jede Verbindung einem Zwischenraum und einer Sammelschiene zu und berechnet die Zeilenhöhen."""
    nodes = graph.nodes
    rows = defaultdict(list)
    for n in nodes.values():
        rows[n.row].append(n)
    n_rows = max(rows) + 1

    down = defaultdict(lambda: defaultdict(list))  # Zwischenraum über Zeile r -> oberer Knoten -> [(Kind, Kante)]
    same = defaultdict(list)  # Zeile -> Kanten innerhalb der Zeile, nicht benachbart
    direct = []  # benachbarte Knoten derselben Zeile: gerade Linie
    for e in graph.edges:
        a, b = nodes[e.a], nodes[e.b]
        if a.row == b.row:
            (direct if abs(a.x - b.x) <= CELL_W + 1 else same[a.row]).append(e)
        else:
            up, lo = (a, b) if a.row < b.row else (b, a)
            down[lo.row][up.id].append((lo, e))

    gaps = {}
    for r in range(n_rows):
        items = []
        for uid, lst in down[r].items():
            xs = [nodes[uid].x] + [c.x for c, _ in lst]
            items.append((min(xs), max(xs), ("d", uid)))
        for i, e in enumerate(same[r]):
            xs = [nodes[e.a].x, nodes[e.b].x]
            items.append((min(xs), max(xs), ("s", i)))
        # Intervall-Färbung: überlappende Schienen bekommen verschiedene Höhen
        lane_end, lane_of = [], {}
        for xmin, xmax, key in sorted(items):
            for li, end in enumerate(lane_end):
                if end < xmin - 14:
                    lane_end[li], lane_of[key] = xmax, li
                    break
            else:
                lane_of[key] = len(lane_end)
                lane_end.append(xmax)
        parents = defaultdict(list)
        for uid, lst in down[r].items():
            for c, e in lst:
                parents[c.id].append(uid)
        for c in parents:
            parents[c].sort(key=lambda uid: nodes[uid].x)
        labelled = [e for lst in down[r].values() for _, e in lst if _edge_text(graph, e, show_ports)]
        stack = max((len(v) for v in parents.values()), default=0) if labelled else 0
        label_room = stack * PORT_H + 4
        height = 16 + len(lane_end) * LANE + label_room if lane_end else (26 if r else 12)
        gaps[r] = {"lane_of": lane_of, "parents": parents, "height": height}

    y = 16
    for r in range(n_rows):
        gaps[r]["top"] = y + 8
        y += gaps[r]["height"]
        for n in rows[r]:
            n.y = y
        y += ICON + max(_label_h(n) for n in rows[r])
    width = max(n.x for n in nodes.values()) + CELL_W / 2
    return down, same, direct, gaps, width, y + 16


def render_png(graph, show_ports=False, scale=2):
    from PIL import Image, ImageDraw

    nodes = graph.nodes
    down, same, direct, gaps, width, height = _plan(graph, show_ports)
    S = scale
    img = Image.new("RGB", (int(width * S), int(height * S)), (255, 255, 255))
    d = ImageDraw.Draw(img)
    f_name, f_sub, f_port = _font(12 * S, bold=True), _font(10 * S), _font(8 * S)

    def line(points, color, w=2, dashed=False):
        pts = [(x * S, y * S) for x, y in points]
        if not dashed:
            d.line(pts, fill=color, width=w * S, joint="curve")
            return
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            length = max(abs(x2 - x1), abs(y2 - y1))
            steps = max(int(length / (6 * S)), 1)
            for i in range(0, steps, 2):
                t1, t2 = i / steps, min((i + 1) / steps, 1)
                d.line(
                    [(x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1), (x1 + (x2 - x1) * t2, y1 + (y2 - y1) * t2)],
                    fill=color, width=w * S,
                )

    def tag(text, x, y, anchor):
        text = _clip(d, text, f_port, (CELL_W - 12) * S)
        tw = d.textlength(text, font=f_port)
        cx = x * S
        cy = y * S - (6 * S if anchor == "mb" else 0)
        d.rounded_rectangle(
            [cx - tw / 2 - 3 * S, cy - 6 * S, cx + tw / 2 + 3 * S, cy + 6 * S],
            radius=2 * S, fill=(255, 255, 255), outline=(215, 215, 215),
        )
        d.text((cx, cy), text, fill=(40, 40, 40), font=f_port, anchor="mm")

    colors = {}

    def color_for(uid):
        if uid not in colors:
            colors[uid] = PALETTE[len(colors) % len(PALETTE)]
        return colors[uid]

    labels = []  # erst nach allen Linien zeichnen, damit sie oben liegen

    for r, groups in sorted(down.items()):
        gap = gaps[r]
        for uid, lst in groups.items():
            u = nodes[uid]
            ly = gap["top"] + gap["lane_of"][("d", uid)] * LANE
            col = EXTERNAL if u.external else color_for(uid)
            entries = []
            for c, e in lst:
                plist = gap["parents"][c.id]
                k = plist.index(uid)
                # mehrere Uplinks in dasselbe Gerät: leicht versetzt einführen
                entries.append((c, e, c.x + (k - (len(plist) - 1) / 2) * 9, len(plist) - 1 - k))
            xs = [u.x] + [ex for _, _, ex, _ in entries]
            u_bottom = u.y + ICON + _label_h(u) - 2
            line([(u.x, u_bottom), (u.x, ly)], col, dashed=u.external)
            if max(xs) > min(xs):
                line([(min(xs), ly), (max(xs), ly)], col, dashed=u.external)
            for c, e, ex, stack_pos in entries:
                dashed = u.external or c.external
                line([(ex, ly), (ex, c.y - 2)], EXTERNAL if dashed else col, w=3 if len(e.labels) > 1 else 2, dashed=dashed)
                if min(xs) < ex < max(xs):  # Abzweig auf der Schiene markieren
                    d.ellipse([(ex - 2.5) * S, (ly - 2.5) * S, (ex + 2.5) * S, (ly + 2.5) * S], fill=col)
                text = _edge_text(graph, e, show_ports)
                if text:
                    labels.append((text, ex, c.y - 3 - stack_pos * PORT_H, "mb"))

    for r, lst in same.items():
        gap = gaps[r]
        for i, e in enumerate(lst):
            a, b = nodes[e.a], nodes[e.b]
            ly = gap["top"] + gap["lane_of"][("s", i)] * LANE
            dashed = a.external or b.external
            line([(a.x, a.y - 2), (a.x, ly), (b.x, ly), (b.x, b.y - 2)], EXTERNAL if dashed else (70, 70, 70), dashed=dashed)
            text = _edge_text(graph, e, show_ports)
            if text:
                labels.append((text, (a.x + b.x) / 2, ly, "mm"))

    for e in direct:
        a, b = nodes[e.a], nodes[e.b]
        dashed = a.external or b.external
        cy = a.y + ICON / 2
        left, right = (a, b) if a.x < b.x else (b, a)
        line(
            [(left.x + ICON / 2 + 4, cy), (right.x - ICON / 2 - 4, cy)],
            EXTERNAL if dashed else (70, 70, 70), w=3 if len(e.labels) > 1 else 2, dashed=dashed,
        )
        text = _edge_text(graph, e, show_ports)
        if text:
            labels.append((text, (a.x + b.x) / 2, cy - 4, "mb"))

    for n in nodes.values():
        pic = Image.open(BytesIO(n.icon)).convert("RGBA").resize((ICON * S, ICON * S), Image.LANCZOS)
        if n.external:
            pic.putalpha(pic.getchannel("A").point(lambda v: int(v * 0.5)))
        img.paste(pic, (int((n.x - ICON / 2) * S), int(n.y * S)), pic)
        ty = (n.y + ICON + 3) * S
        d.text(
            (n.x * S, ty), _clip(d, n.label, f_name, (CELL_W - 8) * S),
            fill=(120, 120, 120) if n.external else (20, 20, 20), font=f_name, anchor="ma",
        )
        for i, sub in enumerate(n.sub):
            d.text((n.x * S, ty + (16 + i * 13) * S), _clip(d, sub, f_sub, (CELL_W - 8) * S), fill=(100, 100, 100), font=f_sub, anchor="ma")

    for text, x, y, anchor in labels:
        tag(text, x, y, anchor)

    # weißen Rand abschneiden: jeder Millimeter kommt der Größe im Dokument zugute
    from PIL import ImageChops

    bbox = ImageChops.difference(img, Image.new("RGB", img.size, (255, 255, 255))).getbbox()
    if bbox:
        pad = 6 * S
        img = img.crop((max(bbox[0] - pad, 0), max(bbox[1] - pad, 0), min(bbox[2] + pad, img.width), min(bbox[3] + pad, img.height)))

    out = BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def _clip(d, text, font, width):
    if d.textlength(text, font=font) <= width:
        return text
    while text and d.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text + "…"
