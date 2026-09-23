"""Topologie-Symbole im Stil von Cisco Packet Tracer (mit Pillow gezeichnet) und ihre Zuordnung zu Geräten."""
import re
from collections import OrderedDict
from functools import lru_cache
from io import BytesIO

# Schlüssel -> (Bezeichnung, Ebene im Diagramm; kleiner = weiter oben)
KINDS = OrderedDict(
    [
        ("cloud", ("Internet / Provider", 0)),
        ("modem", ("Modem / NTU / Medienkonverter", 1)),
        ("firewall", ("Firewall", 1)),
        ("router", ("Router", 1)),
        ("l3switch", ("Layer-3-Switch / Core", 2)),
        ("switch", ("Switch", 3)),
        ("radio", ("Funkstrecke / Richtfunk", 3)),
        ("wlc", ("WLAN-Controller", 3)),
        ("poe", ("PoE-Injektor", 4)),
        ("ap", ("Access Point", 4)),
        ("server", ("Server", 4)),
        ("storage", ("Storage / SAN (MSA)", 4)),
        ("nas", ("NAS", 4)),
        ("tape", ("Bandlaufwerk / Tape Library", 4)),
        ("ups", ("USV / ATS", 4)),
        ("pbx", ("Telefonanlage", 4)),
        ("phone", ("IP-Telefon", 4)),
        ("pc", ("PC / Client", 4)),
        ("printer", ("Drucker", 4)),
        ("camera", ("Kamera", 4)),
        ("generic", ("Sonstiges Gerät", 4)),
    ]
)
HIDDEN = "hidden"
KIND_CHOICES = [(k, v[0]) for k, v in KINDS.items() if k != "cloud"] + [(HIDDEN, "In Topologie ausblenden")]

# Reihenfolge wichtig: erster Treffer gewinnt. None = passiv, nicht zeichnen.
# Tippvarianten („Acces Point“, „Controler“, „Libary“) sind absichtlich mit abgedeckt.
_RULES = [
    (r"patch|panel|\bpdu\b|steckdose|kabel|cable|blank|blind|shelf|fachboden|rangier|\braum\b|\broom\b|halterung|\bmount", None),
    (r"\busv\b|\bups\b|\bats\b|smart-?ups|eaton|\bapc\b|online usv", "ups"),
    (r"poe|injector|injektor", "poe"),
    (r"funk|richtfunk|\bbridge\b|airmax|nanobeam|litebeam|powerbeam|\bptp\b|\bptmp\b|airfiber|siklu", "radio"),
    (r"\brad\b|modem|\bntu\b|\bnt\b|\bont\b|media ?conver|medienkonverter|konverter|\betx-", "modem"),
    (r"firewall|\bfw\b|fw-|sophos|fortigate|fortinet|palo ?alto|\butm\b|\bxgs\b|\bxg\b|watchguard|checkpoint|opnsense|pfsense", "firewall"),
    (r"router|\brtr\b|gateway|\bgw\b|lancom|draytek|fritz|isr\d|asr\d|mikrotik", "router"),
    (r"control+er|\bwlc\b|mobility", "wlc"),
    (r"acc?ess? ?point|\bap\b|\bap-|-ap\b|\bwap\b|wlan|wifi|aironet|unifi ?ap|\biap\b", "ap"),
    (r"\bcore\b|\bl3\b|layer ?3|distribution|\bdist\b|backbone", "l3switch"),
    (r"switch|\bsw\b|\bsw-|-sw\b|catalyst|aruba \d{4}|procurve|\bcbs\d|\bsg\d", "switch"),
    (r"tape|band|\blto\b|libr?ary|storeever|\bmsl\d", "tape"),
    (r"\bnas\b|diskstation|synology|qnap|terastation|readynas|\btvs-|\bds\d{3,4}", "nas"),
    (r"storage|\bsan\b|\bmsa\b|netapp|powervault|eternus|\bme\d{4}", "storage"),
    (r"server|\besx|hyper-?v|\bhost\b|proliant|poweredge|primergy|\bsrv\b|\bvm-?host", "server"),
    (r"telefonanlage|\bpbx\b|\btk-?anlage|starface|3cx|innovaphone|agfeo|auerswald|unify|openscape", "pbx"),
    (r"telefon|phone|\bvoip\b|yealink|snom|gigaset|grandstream", "phone"),
    (r"drucker|printer|\bmfp\b|kyocera|brother|ricoh", "printer"),
    (r"kamera|camera|\bcam\b|axis|hikvision|dahua", "camera"),
    (r"\bpc\b|client|workstation|laptop|notebook|thin ?client|desktop", "pc"),
    (r"sonstig|other|misc", "generic"),
]


def _match(text):
    """(True, kind) beim ersten Treffer, sonst (False, None)."""
    text = text.lower()
    for pattern, kind in _RULES:
        if re.search(pattern, text):
            return True, kind
    return False, None


def guess_kind(device):
    """Symbol raten: zuerst anhand der Rolle, dann Modell/Hersteller. None = passives Gerät (nicht zeichnen)."""
    role = device.role
    found, kind = _match(f"{getattr(role, 'name', '')} {getattr(role, 'slug', '')}")
    if found:
        return kind
    dt = device.device_type
    found, kind = _match(f"{dt.model} {dt.slug} {getattr(dt.manufacturer, 'name', '')}")
    return kind if found else "generic"


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


def _draw_modem(d):
    # flache Box mit LED-Reihe und Glasfaser-/Leitungsanschluss (Modem, NTU, RAD, Medienkonverter)
    _iso_box(d, 12, 58, 100, 88, 12, (70, 84, 100), (130, 146, 162), (52, 64, 78))
    for i, c in enumerate(((60, 200, 90), (60, 200, 90), (250, 190, 40), (60, 200, 90))):
        d.ellipse([22 + i * 12, 68, 28 + i * 12, 74], fill=c)
    d.rectangle([76, 66, 92, 80], fill=(30, 36, 44))
    d.line([(84, 58), (84, 34), (112, 34)], fill=(250, 170, 30), width=4)


def _draw_radio(d):
    # Richtfunk-Antenne auf Mast mit Funkwellen
    d.rectangle([58, 64, 66, 116], fill=(120, 128, 138), outline=OUTLINE)
    d.rectangle([40, 112, 84, 118], fill=(120, 128, 138), outline=OUTLINE)
    d.ellipse([22, 26, 70, 90], fill=(236, 240, 244), outline=OUTLINE, width=3)
    d.ellipse([36, 44, 56, 72], fill=(200, 208, 216), outline=OUTLINE, width=2)
    for r in (14, 24, 34):
        d.arc([74 - r, 58 - r, 74 + r, 58 + r], start=-50, end=50, fill=BLUE, width=5)


def _draw_poe(d):
    # kleine Box mit Blitz
    _iso_box(d, 24, 50, 96, 98, 12, (58, 70, 84), (120, 134, 150), (42, 52, 64))
    d.polygon([(66, 56), (48, 78), (60, 78), (54, 94), (76, 70), (63, 70), (70, 56)], fill=(250, 200, 40), outline=(160, 110, 0))
    d.rectangle([30, 86, 40, 92], fill=(180, 190, 200))
    d.rectangle([80, 86, 90, 92], fill=(180, 190, 200))


def _draw_nas(d):
    # kompakte Box mit vier senkrechten Laufwerksschächten
    _iso_box(d, 22, 30, 98, 108, 12, (54, 60, 70), (110, 118, 130), (38, 44, 52))
    for i in range(4):
        x = 30 + i * 17
        d.rounded_rectangle([x, 40, x + 12, 96], radius=2, fill=(150, 158, 168))
        d.ellipse([x + 4, 88, x + 8, 92], fill=(60, 200, 90))


def _draw_tape(d):
    # Laufwerk mit Kassettenschacht, davor eine LTO-Kassette
    _iso_box(d, 10, 44, 102, 82, 12, (84, 98, 112), (150, 162, 176), (60, 72, 84))
    d.rectangle([22, 56, 72, 64], fill=(24, 28, 34))
    d.ellipse([84, 56, 92, 64], fill=(60, 200, 90))
    d.rounded_rectangle([36, 84, 92, 118], radius=4, fill=(40, 44, 50), outline=OUTLINE, width=2)
    d.rectangle([44, 90, 84, 100], fill=(250, 190, 40))
    d.ellipse([52, 104, 62, 114], fill=(150, 158, 168))
    d.ellipse([68, 104, 78, 114], fill=(150, 158, 168))


def _draw_ups(d):
    # Tower mit Batterie-Symbol
    _iso_box(d, 32, 22, 88, 112, 12, (52, 58, 66), (110, 118, 128), (36, 42, 50))
    d.rounded_rectangle([42, 36, 78, 60], radius=3, fill=(30, 36, 44))
    d.rectangle([46, 42, 70, 54], outline=(60, 200, 90), width=2)
    d.rectangle([70, 45, 74, 51], fill=(60, 200, 90))
    d.rectangle([48, 44, 62, 52], fill=(60, 200, 90))
    d.polygon([(62, 70), (50, 88), (58, 88), (54, 102), (70, 82), (62, 82), (68, 70)], fill=(250, 200, 40))


def _draw_pbx(d):
    # Anlage (Box) mit Hörer-Symbol
    _iso_box(d, 12, 50, 104, 104, 12, (62, 70, 80), (126, 136, 148), (44, 52, 60))
    d.rounded_rectangle([34, 62, 82, 92], radius=12, fill=(236, 240, 244))
    d.rounded_rectangle([40, 70, 50, 86], radius=4, fill=(40, 44, 50))
    d.rounded_rectangle([66, 70, 76, 86], radius=4, fill=(40, 44, 50))
    d.rectangle([46, 70, 70, 76], fill=(40, 44, 50))
    for i in range(3):
        d.ellipse([88, 60 + i * 12, 96, 68 + i * 12], fill=(60, 200, 90))


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
    "modem": _draw_modem,
    "radio": _draw_radio,
    "poe": _draw_poe,
    "nas": _draw_nas,
    "tape": _draw_tape,
    "ups": _draw_ups,
    "pbx": _draw_pbx,
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
