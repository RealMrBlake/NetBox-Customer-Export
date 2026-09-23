"""Topologie-Symbole im Stil von Cisco Packet Tracer (mit Pillow gezeichnet) und ihre Zuordnung zu Geräten."""
import re
from collections import OrderedDict
from functools import lru_cache
from io import BytesIO

# Schlüssel -> (Bezeichnung, Ebene im Diagramm; kleiner = weiter oben)
KINDS = OrderedDict(
    [
        ("cloud", ("Internet / Provider", 0)),
        ("firewall", ("Firewall", 1)),
        ("router", ("Router", 1)),
        ("l3switch", ("Layer-3-Switch / Core", 2)),
        ("switch", ("Switch", 3)),
        ("wlc", ("WLAN-Controller", 3)),
        ("ap", ("Access Point", 4)),
        ("server", ("Server", 4)),
        ("storage", ("Storage / NAS", 4)),
        ("pc", ("PC / Client", 4)),
        ("phone", ("IP-Telefon", 4)),
        ("printer", ("Drucker", 4)),
        ("camera", ("Kamera", 4)),
        ("generic", ("Sonstiges Gerät", 4)),
    ]
)
HIDDEN = "hidden"
KIND_CHOICES = [(k, v[0]) for k, v in KINDS.items() if k != "cloud"] + [(HIDDEN, "In Topologie ausblenden")]

# Reihenfolge wichtig: erster Treffer gewinnt. None = passiv, nicht zeichnen.
_RULES = [
    (r"patch|panel|pdu|steckdose|power|strom|kabel|cable|blank|blind|shelf|fachboden|ups|usv|rangier", None),
    (r"firewall|\bfw\b|fw-|sophos|fortigate|fortinet|palo ?alto|\butm\b|\bxgs\b|\bxg\b|watchguard|checkpoint|opnsense|pfsense", "firewall"),
    (r"router|\brtr\b|gateway|\bgw\b|lancom|draytek|fritz|isr\d|asr\d|mikrotik", "router"),
    (r"controller|\bwlc\b|mobility", "wlc"),
    (r"access ?point|accesspoint|\bap\b|\bap-|-ap\b|\bwap\b|wlan|wifi|aironet|unifi ?ap|\biap\b|instant on ap", "ap"),
    (r"\bcore\b|\bl3\b|layer ?3|distribution|\bdist\b|backbone", "l3switch"),
    (r"switch|\bsw\b|\bsw-|-sw\b|catalyst|aruba \d{4}|procurve|\bcbs\d|\bsg\d", "switch"),
    (r"storage|\bnas\b|\bsan\b|synology|qnap|netapp", "storage"),
    (r"server|\besx|hyper-?v|\bhost\b|proliant|poweredge|\bsrv\b|\bvm-?host", "server"),
    (r"telefon|phone|\bvoip\b|yealink|snom|gigaset", "phone"),
    (r"drucker|printer|\bmfp\b|kyocera|brother|ricoh", "printer"),
    (r"kamera|camera|\bcam\b|axis|hikvision|dahua", "camera"),
    (r"\bpc\b|client|workstation|laptop|notebook|thin ?client|desktop", "pc"),
]


def guess_kind(device):
    """Symbol aus Rolle, Gerätetyp und Hersteller raten. None = passives Gerät (nicht zeichnen)."""
    dt = device.device_type
    role = device.role
    text = " ".join(
        str(x or "")
        for x in (
            getattr(role, "slug", ""), getattr(role, "name", ""),
            dt.model, dt.slug, getattr(dt.manufacturer, "name", ""),
        )
    ).lower()
    for pattern, kind in _RULES:
        if re.search(pattern, text):
            return kind
    return "generic"


# --- Zeichnen -----------------------------------------------------------------

SIZE = 128  # Kantenlänge eines Symbols in Pixeln
BLUE = (29, 96, 158)
BLUE_LIGHT = (86, 149, 206)
BLUE_TOP = (122, 178, 226)
WHITE = (255, 255, 255)
OUTLINE = (20, 55, 95)


def _arrow(d, start, end, color=WHITE, width=5, head=10):
    import math

    d.line([start, end], fill=color, width=width)
    ang = math.atan2(end[1] - start[1], end[0] - start[0])
    left = (end[0] - head * math.cos(ang - 0.5), end[1] - head * math.sin(ang - 0.5))
    right = (end[0] - head * math.cos(ang + 0.5), end[1] - head * math.sin(ang + 0.5))
    d.polygon([end, left, right], fill=color)


def _iso_box(d, x1, y1, x2, y2, depth, front, top, side=None):
    """Quader in leichter Aufsicht: Front + Oberseite."""
    d.polygon([(x1, y1), (x1 + depth, y1 - depth), (x2 + depth, y1 - depth), (x2, y1)], fill=top, outline=OUTLINE)
    if side:
        d.polygon([(x2, y1), (x2 + depth, y1 - depth), (x2 + depth, y2 - depth), (x2, y2)], fill=side, outline=OUTLINE)
    d.rectangle([x1, y1, x2, y2], fill=front, outline=OUTLINE, width=2)


def _cylinder(d, x1, y1, x2, y2, ry, body, top):
    d.rectangle([x1, y1 + ry, x2, y2 - ry], fill=body)
    d.ellipse([x1, y2 - 2 * ry, x2, y2], fill=body, outline=OUTLINE, width=2)
    d.rectangle([x1 + 1, y1 + ry, x2 - 1, y2 - ry], fill=body)
    d.line([(x1, y1 + ry), (x1, y2 - ry)], fill=OUTLINE, width=2)
    d.line([(x2, y1 + ry), (x2, y2 - ry)], fill=OUTLINE, width=2)
    d.ellipse([x1, y1, x2, y1 + 2 * ry], fill=top, outline=OUTLINE, width=2)


def _draw_router(d):
    _cylinder(d, 14, 34, 114, 100, 18, BLUE, BLUE_TOP)
    # Packet-Tracer-typisch: zwei Pfeile nach außen, zwei nach innen (auf der Oberseite)
    cx, cy = 64, 52
    _arrow(d, (cx + 8, cy + 3), (cx + 40, cy + 12), width=4, head=9)
    _arrow(d, (cx - 8, cy - 3), (cx - 40, cy - 12), width=4, head=9)
    _arrow(d, (cx + 40, cy - 12), (cx + 10, cy - 3), width=4, head=9)
    _arrow(d, (cx - 40, cy + 12), (cx - 10, cy + 3), width=4, head=9)


def _draw_switch(d, l3=False):
    _iso_box(d, 8, 64, 98, 98, 24, BLUE, BLUE_TOP, BLUE_LIGHT)
    # Doppelpfeile auf der Oberseite (Packet-Tracer-Switch)
    _arrow(d, (28, 47), (90, 47), width=5, head=11)
    _arrow(d, (92, 56), (30, 56), width=5, head=11)
    if l3:
        from PIL import ImageFont

        try:
            font = ImageFont.load_default(size=20)
        except TypeError:  # Pillow < 10.1
            font = ImageFont.load_default()
        d.text((53, 81), "L3", fill=WHITE, font=font, anchor="mm")
    else:
        for i in range(8):  # Ports
            d.rectangle([16 + i * 10, 84, 22 + i * 10, 90], fill=BLUE_TOP)


def _draw_firewall(d):
    red, mortar = (196, 64, 44), (240, 220, 200)
    _iso_box(d, 16, 40, 100, 104, 12, red, (226, 110, 88), (160, 50, 36))
    for row, y in enumerate(range(40, 104, 13)):
        d.line([(16, y), (100, y)], fill=mortar, width=2)
        off = 0 if row % 2 else 14
        for x in range(16 + off, 100, 28):
            d.line([(x, y), (x, min(y + 13, 104))], fill=mortar, width=2)
    d.rectangle([16, 40, 100, 104], outline=OUTLINE, width=2)


def _draw_ap(d):
    d.rounded_rectangle([22, 72, 106, 96], radius=10, fill=BLUE, outline=OUTLINE, width=2)
    d.ellipse([56, 78, 72, 90], fill=BLUE_TOP)
    for r in (16, 28, 40):
        d.arc([64 - r, 62 - r, 64 + r, 62 + r], start=220, end=320, fill=BLUE, width=5)


def _draw_wlc(d):
    _iso_box(d, 10, 66, 104, 96, 12, BLUE, BLUE_TOP, BLUE_LIGHT)
    for r in (12, 22, 32):
        d.arc([57 - r, 52 - r, 57 + r, 52 + r], start=215, end=325, fill=BLUE, width=5)


def _draw_server(d):
    d.rectangle([38, 14, 90, 114], fill=(84, 98, 112), outline=OUTLINE, width=2)
    d.polygon([(38, 14), (48, 6), (100, 6), (90, 14)], fill=(140, 154, 168), outline=OUTLINE)
    d.polygon([(90, 14), (100, 6), (100, 106), (90, 114)], fill=(60, 72, 84), outline=OUTLINE)
    for y in range(24, 96, 14):
        d.rectangle([45, y, 83, y + 8], fill=(200, 208, 216))
        d.ellipse([76, y + 2, 80, y + 6], fill=(60, 200, 90))


def _draw_storage(d):
    grey, top = (104, 116, 130), (176, 188, 200)
    for y in (70, 46, 22):
        _cylinder(d, 22, y, 106, y + 36, 10, grey, top)


def _draw_pc(d):
    d.rounded_rectangle([18, 16, 110, 82], radius=6, fill=(50, 56, 64), outline=OUTLINE, width=2)
    d.rectangle([26, 24, 102, 74], fill=BLUE_LIGHT)
    d.polygon([(54, 82), (74, 82), (80, 100), (48, 100)], fill=(84, 92, 100))
    d.rounded_rectangle([34, 100, 94, 108], radius=3, fill=(84, 92, 100))


def _draw_phone(d):
    d.rounded_rectangle([30, 52, 104, 106], radius=8, fill=(60, 66, 74), outline=OUTLINE, width=2)
    d.rectangle([62, 60, 96, 76], fill=BLUE_LIGHT)
    for i in range(3):
        for j in range(3):
            d.rectangle([64 + j * 11, 82 + i * 7, 70 + j * 11, 86 + i * 7], fill=(200, 200, 200))
    d.rounded_rectangle([18, 32, 50, 100], radius=10, fill=(40, 44, 50), outline=OUTLINE, width=2)


def _draw_printer(d):
    d.rectangle([40, 18, 88, 50], fill=WHITE, outline=OUTLINE, width=2)
    _iso_box(d, 16, 50, 104, 94, 10, (96, 104, 114), (150, 158, 168))
    d.rectangle([40, 86, 88, 108], fill=WHITE, outline=OUTLINE, width=2)
    d.ellipse([90, 60, 98, 68], fill=(60, 200, 90))


def _draw_camera(d):
    d.rounded_rectangle([20, 44, 92, 80], radius=10, fill=(230, 232, 236), outline=OUTLINE, width=2)
    d.ellipse([84, 48, 110, 76], fill=(40, 44, 50), outline=OUTLINE, width=2)
    d.ellipse([92, 56, 102, 68], fill=BLUE_LIGHT)
    d.rectangle([48, 80, 58, 104], fill=(150, 156, 164))
    d.rectangle([34, 104, 74, 110], fill=(150, 156, 164))


def _draw_cloud(d):
    blobs = [(14, 52, 58, 96), (36, 30, 84, 78), (68, 38, 112, 86), (46, 60, 100, 104), (22, 64, 62, 104)]
    for x1, y1, x2, y2 in blobs:
        d.ellipse([x1 - 3, y1 - 3, x2 + 3, y2 + 3], fill=BLUE)
    for x1, y1, x2, y2 in blobs:
        d.ellipse([x1, y1, x2, y2], fill=(236, 244, 252))


def _draw_generic(d):
    _iso_box(d, 16, 44, 104, 96, 12, (120, 132, 146), (176, 186, 198), (96, 106, 118))
    for i in range(4):
        d.rectangle([26 + i * 18, 76, 38 + i * 18, 86], fill=(200, 208, 216))


_DRAWERS = {
    "router": _draw_router,
    "switch": _draw_switch,
    "l3switch": lambda d: _draw_switch(d, l3=True),
    "firewall": _draw_firewall,
    "ap": _draw_ap,
    "wlc": _draw_wlc,
    "server": _draw_server,
    "storage": _draw_storage,
    "pc": _draw_pc,
    "phone": _draw_phone,
    "printer": _draw_printer,
    "camera": _draw_camera,
    "cloud": _draw_cloud,
    "generic": _draw_generic,
}


@lru_cache(maxsize=None)
def builtin_icon(kind):
    """PNG-Bytes eines eingebauten Symbols (SIZE x SIZE, transparent)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    _DRAWERS.get(kind, _draw_generic)(ImageDraw.Draw(img))
    out = BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def fit_icon(data):
    """Beliebiges Bild (Bytes) auf SIZE x SIZE mit Seitenverhältnis einpassen, transparent auffüllen."""
    from PIL import Image

    src = Image.open(BytesIO(data)).convert("RGBA")
    src.thumbnail((SIZE, SIZE), Image.LANCZOS)
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    img.paste(src, ((SIZE - src.width) // 2, (SIZE - src.height) // 2), src)
    out = BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


class SymbolResolver:
    """Ermittelt Symbol (kind) und Icon für ein Gerät: Gerätetyp-Zuordnung > Rollen-Zuordnung > Heuristik."""

    def __init__(self):
        from django.db import DatabaseError

        from .models import TopologySymbol

        self.by_type, self.by_role = {}, {}
        try:
            for s in TopologySymbol.objects.all():
                if s.device_type_id:
                    self.by_type[s.device_type_id] = s
                elif s.role_id:
                    self.by_role[s.role_id] = s
        except DatabaseError:  # Migration noch nicht ausgeführt
            pass
        self._icons = {}

    def resolve(self, device):
        """(kind, icon_png_bytes) oder (None, None), wenn das Gerät nicht gezeichnet wird."""
        sym = self.by_type.get(device.device_type_id) or self.by_role.get(device.role_id)
        if sym:
            if sym.kind == HIDDEN:
                return None, None
            kind = sym.kind or guess_kind(device) or "generic"
            if sym.icon:
                return kind, self._custom_icon(sym)
            return kind, builtin_icon(kind)
        kind = guess_kind(device)
        return (kind, builtin_icon(kind)) if kind else (None, None)

    def _custom_icon(self, sym):
        if sym.pk not in self._icons:
            try:
                with sym.icon.open("rb") as f:
                    self._icons[sym.pk] = fit_icon(f.read())
            except (OSError, ValueError):
                self._icons[sym.pk] = builtin_icon(sym.kind or "generic")
        return self._icons[sym.pk]
