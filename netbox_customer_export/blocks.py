"""Neutrales Dokumentmodell, das sowohl der HTML/PDF- als auch der Word-Renderer versteht."""
import base64
from dataclasses import dataclass, field

from django.utils.text import slugify

EMPTY = "—"


@dataclass
class Block:
    kind: str  # heading | paragraph | table | kv | images | pagebreak
    level: int = 0
    text: str = ""
    headers: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    images: list = field(default_factory=list)
    anchor: str = ""


@dataclass
class Document:
    title: str
    subtitle: str
    blocks: list
    meta: dict
    branding: dict = field(default_factory=dict)

    @property
    def toc(self):
        out = []
        for b in self.blocks:
            headings = b.rows if b.kind == "landscape" else [b]
            out += [h for h in headings if h.kind == "heading" and h.level <= 2]
        return out


_anchor_counter = {"n": 0}


def H(level, text):
    _anchor_counter["n"] += 1
    return Block("heading", level=level, text=str(text), anchor=f"s{_anchor_counter['n']}-{slugify(str(text))[:40]}")


def P(text):
    return Block("paragraph", text=str(text))


def T(headers, rows):
    return Block("table", headers=list(headers), rows=[[fmt(c) for c in r] for r in rows])


def KV(pairs, skip_empty=True):
    rows = [[k, fmt(v)] for k, v in pairs if not (skip_empty and v in (None, "", [], EMPTY))]
    return Block("kv", rows=rows)


def IMAGES(images, wide=False):
    """images: Liste von (svg_string oder None, caption, png_bytes_oder_None)."""
    out = []
    for svg, caption, png in images:
        if svg:
            data_uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
        elif png:
            data_uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        else:
            continue
        out.append({"svg": svg, "png": png, "caption": caption, "data_uri": data_uri})
    return Block("images", images=out, level=1 if wide else 0)  # level=1: volle Seitenbreite


def LANDSCAPE(headings, png):
    """Eigene Seite im Querformat: Überschriften + Bild so groß wie möglich (z.B. Topologie)."""
    data_uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    return Block("landscape", rows=list(headings), images=[{"svg": None, "png": png, "caption": "", "data_uri": data_uri}])


def PAGEBREAK():
    return Block("pagebreak")


def fmt(value):
    if value is None or value == "":
        return EMPTY
    if isinstance(value, bool):
        return "Ja" if value else "Nein"
    if isinstance(value, (list, tuple, set)) or hasattr(value, "all"):
        items = value.all() if hasattr(value, "all") else value
        return ", ".join(str(i) for i in items) or EMPTY
    return str(value)


def get(obj, path):
    """Dotted-getattr, bevorzugt get_<feld>_display() für Choice-Felder."""
    for part in path.split("."):
        if obj is None:
            return None
        display = getattr(obj, f"get_{part}_display", None)
        obj = display() if callable(display) else getattr(obj, part, None)
    return obj
