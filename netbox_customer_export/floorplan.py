"""Raumpläne aus dem Plugin NetBox-FloorPlan (netbox_floorplanner.FloorPlan / FloorPlanItem).

Optional: Ohne das Plugin liefert ``is_installed()`` False und der Abschnitt bleibt leer.
Es wird nichts aus ``netbox_floorplanner`` importiert, Modelle kommen nur über die App-Registry.
Das SVG ist eigenständig (feste Farben, eingebettetes Hintergrundbild), damit es in PDF und Word
(cairosvg) gleich aussieht; für Word ohne cairosvg gibt es ein vereinfachtes Pillow-PNG.
"""
import base64
import math
from io import BytesIO

from django.apps import apps
from django.db.models import Q
from django.utils.html import escape

from .blocks import H, IMAGES, KV, P, T

APP = "netbox_floorplanner"

TYPE_COLORS = {
    "area": "#22c55e", "wall": "#475569", "door": "#b45309", "window": "#0ea5e9", "column": "#64748b",
    "rack": "#3b82f6", "device": "#8b5cf6", "cooling": "#06b6d4", "power": "#f59e0b", "label": "#334155",
}
FILLED = ("rack", "device", "cooling", "power")
FLOOR, WALL, MUTED = "#ffffff", "#334155", "#6c757d"


def is_installed():
    if not apps.is_installed(APP):
        return False
    try:
        apps.get_model(APP, "FloorPlan")
        apps.get_model(APP, "FloorPlanItem")
    except LookupError:
        return False
    return True


def _models():
    return apps.get_model(APP, "FloorPlan"), apps.get_model(APP, "FloorPlanItem")


def floorplans(scope):
    """Raumpläne im Scope. Mandanten: Pläne des Mandanten oder mit dessen Racks/Geräten."""
    FloorPlan, _ = _models()
    if scope.kind == "site":
        q = Q(site=scope.obj)
    elif scope.kind == "location":
        q = Q(location__in=scope.locations)
    else:
        q = Q(tenant__in=scope.tenants) | Q(items__rack__tenant__in=scope.tenants) | Q(items__device__tenant__in=scope.tenants)
    qs = FloorPlan.objects.filter(q).distinct().select_related("site", "location", "tenant")
    return scope.restrict(qs).order_by("site__name", "location__name", "name")


def meters(cm):
    return f"{cm / 100:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _items(plan):
    _, Item = _models()
    return list(Item.objects.filter(floorplan=plan).select_related("rack", "device").order_by("z_index", "pk"))


def _text(item):
    return item.label or (item.rack.name if item.rack_id else item.device.name if item.device_id else "")


def _shade(hex_color, f=0.7):
    try:
        n = int(hex_color.lstrip("#"), 16)
    except ValueError:
        return hex_color
    return "#{:02x}{:02x}{:02x}".format(*(round(((n >> s) & 255) * f) for s in (16, 8, 0)))


def _color(item):
    c = item.color or TYPE_COLORS.get(item.item_type, "#868e96")
    return c if len(c) == 7 and c.startswith("#") else "#868e96"


# --- SVG ----------------------------------------------------------------------

def _item_svg(item):
    x, y, w, h, t = item.x, item.y, item.width, item.height, item.item_type
    cx, cy = x + w / 2, y + h / 2
    color = _color(item)
    sw = 'stroke-width="3"'
    parts = []
    if t == "area":
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="{color}" fill-opacity="0.12" stroke="{color}" {sw} stroke-dasharray="12 6"/>')
    elif t in ("wall", "door"):
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}"/>')
        if t == "door":
            parts.append(f'<path d="M {x + w} {y} A {w} {w} 0 0 0 {x} {y - w} L {x} {y}" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="2" stroke-dasharray="6 4"/>')
    elif t == "window":
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{FLOOR}" stroke="{color}" {sw}/>')
    elif t == "column":
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}" fill-opacity="0.35" stroke="{color}" {sw}/>'
                     f'<path d="M {x} {y} L {x + w} {y + h} M {x + w} {y} L {x} {y + h}" stroke="{color}" stroke-width="2"/>')
    elif t in FILLED:
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" fill="{color}" fill-opacity="0.85" stroke="{_shade(color)}" {sw}/>')
        if t == "rack":
            fh = min(h * 0.12, 10)
            parts.append(f'<rect x="{x}" y="{y + h - fh}" width="{w}" height="{fh}" fill="{_shade(color)}"/>')
    text = _text(item)
    if text:
        fs = max(8, h * 0.6) if t == "label" else max(6, min(h * 0.3, (w * 1.6) / max(len(text), 3), 60))
        fill = "#ffffff" if t in FILLED else color if t == "label" else _shade(color)
        anchor, tx, ty = ("start", x + fs * 0.5, y + fs * 1.2) if t == "area" else ("middle", cx, cy)
        flip = f' transform="rotate(180 {tx} {ty})"' if 90 < item.rotation % 360 <= 270 else ""
        parts.append(f'<text x="{tx}" y="{ty}" dy="0.35em" font-size="{fs:.1f}" font-weight="bold" text-anchor="{anchor}" fill="{fill}"{flip}>{escape(text)}</text>')
    transform = f' transform="rotate({item.rotation} {cx} {cy})"' if item.rotation else ""
    return f'<g{transform}>{"".join(parts)}</g>'


def _background(plan):
    """Hintergrundbild als (Bytes, MIME) oder None."""
    if not plan.background_image:
        return None
    try:
        with plan.background_image.open("rb") as f:
            data = f.read()
    except Exception:  # noqa: BLE001 – Datei fehlt o.Ä.: Plan ohne Hintergrund
        return None
    mime = "image/jpeg" if data[:2] == b"\xff\xd8" else "image/png" if data[:4] == b"\x89PNG" else "image/webp" if data[8:12] == b"WEBP" else "image/gif"
    return data, mime


def render_svg(plan, items):
    width, depth = plan.width, plan.depth
    fs = max(10, min(max(width, depth) * 0.025, 200))
    m = fs * 2
    bg = ""
    if (b := _background(plan)) and b[1] in ("image/jpeg", "image/png"):
        uri = f"data:{b[1]};base64," + base64.b64encode(b[0]).decode("ascii")
        bg = f'<image href="{uri}" xlink:href="{uri}" x="0" y="0" width="{width}" height="{depth}" preserveAspectRatio="none" opacity="{plan.background_opacity / 100}"/>'
    vw, vh = width + 2 * m, depth + 2 * m
    px = 1600 / vw  # feste Pixelgröße für Renderer ohne viewBox-Skalierung
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{vw * px:.0f}" height="{vh * px:.0f}" viewBox="{-m} {-m} {vw} {vh}" font-family="DejaVu Sans, Arial, sans-serif">'
        f'<rect x="{-m}" y="{-m}" width="{vw}" height="{vh}" fill="#ffffff"/>'
        f'<rect x="0" y="0" width="{width}" height="{depth}" fill="{FLOOR}"/>{bg}'
        f'{"".join(_item_svg(i) for i in items)}'
        f'<rect x="0" y="0" width="{width}" height="{depth}" fill="none" stroke="{WALL}" stroke-width="{max(4, fs * 0.15):.1f}"/>'
        f'<text x="{width / 2}" y="{-fs * 0.6}" font-size="{fs:.1f}" text-anchor="middle" fill="{MUTED}">{meters(width)} m</text>'
        f'<text transform="translate({-fs * 0.6} {depth / 2}) rotate(-90)" font-size="{fs:.1f}" text-anchor="middle" fill="{MUTED}">{meters(depth)} m</text>'
        f"</svg>"
    )


# --- PNG (Pillow, für Word ohne cairosvg) ---------------------------------------

def _rgb(hex_color):
    n = int(hex_color.lstrip("#"), 16)
    return (n >> 16) & 255, (n >> 8) & 255, n & 255


def _mix(rgb, alpha, base=(255, 255, 255)):
    return tuple(round(c * alpha + b * (1 - alpha)) for c, b in zip(rgb, base))


def render_png(plan, items):
    from PIL import Image, ImageDraw

    from .rack_png import _font

    width, depth = plan.width, plan.depth
    fs = max(10, min(max(width, depth) * 0.025, 200))
    m = fs * 2
    s = 1600 / (width + 2 * m)
    img = Image.new("RGB", (round((width + 2 * m) * s), round((depth + 2 * m) * s)), "white")
    if (b := _background(plan)):
        try:
            bgi = Image.open(BytesIO(b[0])).convert("RGB").resize((max(1, round(width * s)), max(1, round(depth * s))))
            img.paste(Image.blend(Image.new("RGB", bgi.size, "white"), bgi, plan.background_opacity / 100), (round(m * s), round(m * s)))
        except Exception:  # noqa: BLE001
            pass
    d = ImageDraw.Draw(img)

    def pt(px_, py_):
        return (px_ + m) * s, (py_ + m) * s

    for item in items:
        x, y, w, h, t = item.x, item.y, item.width, item.height, item.item_type
        cx, cy = x + w / 2, y + h / 2
        a = math.radians(item.rotation or 0)

        def rot(px_, py_):
            dx, dy = px_ - cx, py_ - cy
            return pt(cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a))

        poly = [rot(x, y), rot(x + w, y), rot(x + w, y + h), rot(x, y + h)]
        c = _rgb(_color(item))
        if t == "area":
            d.polygon(poly, fill=_mix(c, 0.12), outline=c, width=2)
        elif t in ("wall", "door"):
            d.polygon(poly, fill=c)
        elif t == "window":
            d.polygon(poly, fill=(255, 255, 255), outline=c, width=2)
        elif t == "column":
            d.polygon(poly, fill=_mix(c, 0.35), outline=c, width=2)
            d.line([poly[0], poly[2]], fill=c, width=1)
            d.line([poly[1], poly[3]], fill=c, width=1)
        elif t in FILLED:
            d.polygon(poly, fill=_mix(c, 0.85), outline=_rgb(_shade(_color(item))), width=2)
        text = _text(item)
        if text:
            size = max(8, h * 0.6) if t == "label" else max(6, min(h * 0.3, (w * 1.6) / max(len(text), 3), 60))
            # bei 90°/270° steht der Text quer – dann an der Höhe statt der Breite ausrichten
            vertical = 45 < (item.rotation or 0) % 180 < 135
            if vertical and t != "label":
                size = max(6, min(w * 0.3, (h * 1.6) / max(len(text), 3), 60))
            fill = (255, 255, 255) if t in FILLED else c if t == "label" else _rgb(_shade(_color(item)))
            font = _font(max(8, round(size * s)))
            if t == "area":
                d.text(rot(x + size * 0.5, y + size * 1.2), text, fill=fill, font=font, anchor="lm")
            else:
                d.text(pt(cx, cy), text, fill=fill, font=font, anchor="mm")
    d.rectangle([pt(0, 0), pt(width, depth)], outline=_rgb(WALL), width=3)
    font = _font(max(10, round(fs * s)))
    d.text(pt(width / 2, -fs * 0.6), f"{meters(width)} m", fill=_rgb(MUTED), font=font, anchor="ms")
    label = Image.new("RGBA", (round(fs * s * 8), round(fs * s * 1.6)), (255, 255, 255, 0))
    ImageDraw.Draw(label).text((label.width / 2, label.height / 2), f"{meters(depth)} m", fill=_rgb(MUTED), font=font, anchor="mm")
    label = label.rotate(90, expand=True)
    lx, ly = pt(-fs * 0.6, depth / 2)
    img.paste(label, (round(lx - label.width * 0.7), round(ly - label.height / 2)), label)
    out = BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


# --- Abschnitt ----------------------------------------------------------------

def floorplan_blocks(scope, opts):
    blocks = []
    for plan in floorplans(scope):
        items = _items(plan)
        where = " / ".join(str(x) for x in (plan.site, plan.location) if x)
        blocks.append(H(2, f"{plan.name} ({where})" if where else plan.name))
        blocks.append(
            KV(
                [
                    ("Standort", plan.site),
                    ("Lokation", plan.location),
                    ("Mandant", plan.tenant),
                    ("Raumgröße", f"{meters(plan.width)} × {meters(plan.depth)} m"),
                    ("Beschreibung", plan.description),
                ]
            )
        )
        svg, png, error = None, None, None
        try:
            svg = render_svg(plan, items)
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {e}"
        if opts.get("format") == "docx" or not svg:
            try:
                png = render_png(plan, items)
            except Exception as e:  # noqa: BLE001
                error = f"{error or ''} / PNG: {type(e).__name__}: {e}".strip(" /")
        if svg or png:
            blocks.append(IMAGES([(svg, "", png)], wide=True))
        else:
            blocks.append(P(f"Raumplan konnte nicht erzeugt werden: {error}"))
        placed = [i for i in items if i.rack_id or i.device_id]
        if placed and opts.get("floorplan_objects", True):
            rows = []
            for i in sorted(placed, key=lambda i: _text(i).lower()):
                obj = i.rack or i.device
                kind = "Rack" if i.rack_id else "Gerät"
                rows.append([obj.name or str(obj), kind, i.label if i.label and i.label != obj.name else None])
            blocks.append(T(["Name", "Art", "Beschriftung im Plan"], rows))
        if plan.comments:
            blocks.append(P(plan.comments))
    return blocks
