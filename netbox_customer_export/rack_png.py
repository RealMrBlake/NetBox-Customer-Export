"""Rack-Ansicht als PNG mit Pillow (in NetBox ohnehin installiert).

Wird für Word genutzt, wenn cairosvg nicht verfügbar ist oder das SVG nicht erzeugt werden konnte.
"""
from io import BytesIO

SCALE = 2
UNIT_H = 22 * SCALE
BODY_W = 220 * SCALE
LEGEND_W = 30 * SCALE
MARGIN = 15 * SCALE
FRAME = 3 * SCALE

BG = (255, 255, 255)
RACK_BG = (245, 245, 245)
FRAME_COLOR = (80, 80, 80)
GRID = (215, 215, 215)
LEGEND_TEXT = (110, 110, 110)
FALLBACK_ROLE = (158, 158, 158)


def _font(size):
    from PIL import ImageFont

    for name in ("DejaVuSans.ttf", "Arial.ttf", "arial.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _hex(color):
    color = (color or "").lstrip("#")
    if len(color) != 6:
        return FALLBACK_ROLE
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))


def _text_color(rgb):
    r, g, b = rgb
    return (0, 0, 0) if (r * 299 + g * 587 + b * 114) / 1000 > 140 else (255, 255, 255)


def _fit(draw, text, font, width):
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text + "…"


def render_rack_png(rack, face, devices):
    """devices: iterierbare Geräte des Racks (bereits nach Berechtigung gefiltert)."""
    from PIL import Image, ImageDraw

    units = int(rack.u_height)
    start = int(getattr(rack, "starting_unit", 1) or 1)
    desc = bool(getattr(rack, "desc_units", False))
    width = MARGIN * 2 + LEGEND_W + BODY_W
    height = MARGIN * 2 + units * UNIT_H
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)
    small, normal = _font(10 * SCALE), _font(11 * SCALE)

    left, top = MARGIN + LEGEND_W, MARGIN
    draw.rectangle([left, top, left + BODY_W, top + units * UNIT_H], fill=RACK_BG)

    def y_of(unit):
        """Obere Kante einer Höheneinheit (unit = Nummer wie in NetBox)."""
        idx = unit - start  # 0 = unterste HE
        row = idx if desc else units - 1 - idx
        return top + row * UNIT_H

    for i in range(units):
        unit = start + i
        y = y_of(unit)
        draw.line([left, y, left + BODY_W, y], fill=GRID)
        label = str(unit)
        draw.text((left - 6 * SCALE - draw.textlength(label, font=small), y + UNIT_H / 2), label, fill=LEGEND_TEXT, font=small, anchor="lm")

    for d in devices:
        if d.position is None:
            continue
        on_face = d.face == face or getattr(d.device_type, "is_full_depth", False)
        if not on_face:
            continue
        pos, u = float(d.position), float(d.device_type.u_height or 0)
        if u <= 0:
            continue
        # Gerät belegt [pos, pos+u); stetig gerechnet, damit auch halbe HE passen
        offset = (pos - start) if desc else (units - (pos - start) - u)
        y1 = top + offset * UNIT_H
        y2 = y1 + u * UNIT_H
        fill = _hex(d.role.color if d.role else None)
        rear_only = d.face != face  # Full-Depth-Gerät von der anderen Seite: aufgehellt
        if rear_only:
            fill = tuple(int(c + (255 - c) * 0.55) for c in fill)
        draw.rectangle([left + 1, y1 + 1, left + BODY_W - 1, y2 - 1], fill=fill, outline=FRAME_COLOR)
        name = _fit(draw, d.name or str(d.device_type), normal, BODY_W - 12 * SCALE)
        draw.text((left + BODY_W / 2, (y1 + y2) / 2), name, fill=_text_color(fill), font=normal, anchor="mm")

    draw.rectangle([left, top, left + BODY_W, top + units * UNIT_H], outline=FRAME_COLOR, width=FRAME)

    out = BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()
