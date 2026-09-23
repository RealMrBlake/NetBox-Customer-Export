"""Rack-Ansichten offline (ohne HTTP-Aufruf der API) als SVG erzeugen."""
import base64
import logging
import mimetypes
import re

from django.utils.module_loading import import_string
from netbox.plugins import get_plugin_config

logger = logging.getLogger("netbox_customer_export")

# NetBox-Standardwerte der Rack-Ansicht
UNIT_WIDTH = 220
UNIT_HEIGHT = 22
LEGEND_WIDTH = 30
MARGIN_WIDTH = 15


def device_image(device_type, face):
    """Bilddatei (FieldFile) des Gerätetyps für die Seite oder None."""
    image = getattr(device_type, "front_image" if face == "front" else "rear_image", None)
    return image if image else None


def _data_uri(image):
    mime = mimetypes.guess_type(image.name)[0] or "image/png"
    with image.open("rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode('ascii')}"


def _inline_images(svg, devices):
    """Ersetzt die /media/…-Links der Gerätebilder durch eingebettete Daten.

    Word, WeasyPrint und <img src="data:image/svg+xml…"> laden keine externen (login-geschützten) Dateien nach.
    """
    seen = set()
    for d in devices:
        for face in ("front", "rear"):
            image = device_image(d.device_type, face)
            if not image or image.name in seen:
                continue
            seen.add(image.name)
            try:
                svg = svg.replace(f'"{image.url}"', f'"{_data_uri(image)}"')
            except OSError:
                logger.warning("Gerätebild %s nicht lesbar", image.name)
    return svg


# Helles NetBox-Theme mit festen Werten. Das Original-Stylesheet nutzt CSS-Variablen (var(--nbx-…)),
# die WeasyPrint und cairosvg nicht auflösen. Leere HE würden sonst schwarz gefüllt.
STATIC_CSS = """
svg { font-family: Helvetica, Arial, sans-serif; font-size: 11px; }
text { text-anchor: middle; dominant-baseline: middle; }
.unit { fill: #6c757d; }
.hidden { visibility: hidden; }
rect.shaded, image.shaded { opacity: .25; }
text.shaded { opacity: .5; }
.rack { fill: none; stroke-width: 2px; stroke: #000000; }
.slot { fill: #e9ecef; stroke: #adb5bd; }
.slot.occupied[class] { fill: url(#occupied); }
.slot.blocked[class] { fill: url(#blocked); }
.reservation[class] { fill: url(#reserved); }
"""

# class -> Präsentationsattribute (Fallback, falls der Renderer <style> ignoriert)
_CLASS_ATTRS = (
    ("occupied", {"fill": "url(#occupied)", "stroke": "#adb5bd"}),
    ("blocked", {"fill": "url(#blocked)", "stroke": "#adb5bd"}),
    ("reservation", {"fill": "url(#reserved)"}),
    ("slot", {"fill": "#e9ecef", "stroke": "#adb5bd"}),
    ("rack", {"fill": "none", "stroke": "#000000", "stroke-width": "2"}),
    ("unit", {"fill": "#6c757d"}),
    ("hidden", {"visibility": "hidden"}),
)
_TAG_WITH_CLASS = re.compile(r'<(rect|text|image|path|line)\b([^<>]*?)\sclass="([^"]*)"([^<>]*?)(/?)>')


def _apply_class_attrs(match):
    tag, before, classes, after, close = match.groups()
    names = classes.split()
    attrs = {}
    for cls, values in _CLASS_ATTRS:
        if cls in names:
            attrs = {**values, **attrs}  # spezifischere Klassen (weiter oben) gewinnen
    if "shaded" in names:
        attrs["opacity"] = "0.5" if tag == "text" else "0.25"
    existing = before + after
    extra = "".join(f' {k}="{v}"' for k, v in attrs.items() if f" {k}=" not in existing)
    return f'<{tag}{before} class="{classes}"{after}{extra}{close}>'


def normalize_svg(svg):
    """Macht das NetBox-SVG druck- und renderertauglich (feste Farben, keine Hover-Texte)."""
    svg = re.sub(r"<style[^>]*>.*?</style>", f"<style>{STATIC_CSS}</style>", svg, count=1, flags=re.S)
    # "Add Device"-Texte sind nur per Hover sichtbar – im Dokument entfernen
    svg = re.sub(r'<text\b[^>]*class="[^"]*add-device[^"]*"[^>]*>.*?</text>', "", svg, flags=re.S)
    return _TAG_WITH_CLASS.sub(_apply_class_attrs, svg)


def render_rack_svg(rack, face, user, images=False, devices=()):
    """Gibt (svg, fehler) zurück – genau einer der beiden Werte ist None.

    Ist ``rack_svg_renderer`` gesetzt (z.B. der Offline-Renderer aus Netbox-Utilities, der mehrere
    Geräte pro HE korrekt darstellt), wird dieser aufgerufen: ``fn(rack=..., face=..., user=..., images=...)``.
    Andernfalls wird NetBox' eigener RackElevationSVG direkt in-process genutzt.
    """
    try:
        renderer = get_plugin_config("netbox_customer_export", "rack_svg_renderer")
        if renderer:
            fn = import_string(renderer)
            try:
                svg = fn(rack=rack, face=face, user=user, images=images)
            except TypeError:  # ältere Adapter ohne images-Parameter
                svg = fn(rack=rack, face=face, user=user)
        else:
            from dcim.svg import RackElevationSVG

            # Maße explizit übergeben: je nach NetBox-Version fehlen die RACK_ELEVATION_DEFAULT_*-Parameter
            # in der Konfiguration, dann bricht der Renderer mit AttributeError ab.
            svg = RackElevationSVG(
                rack,
                unit_width=UNIT_WIDTH,
                unit_height=UNIT_HEIGHT,
                legend_width=LEGEND_WIDTH,
                margin_width=MARGIN_WIDTH,
                user=user,
                include_images=images,
                base_url="",
            ).render(face)
        svg = svg.tostring() if hasattr(svg, "tostring") else str(svg)
        svg = normalize_svg(svg)
        if images:
            svg = _inline_images(svg, devices)
        return svg, None
    except Exception as e:  # noqa: BLE001 – ein defektes Rack soll nicht den ganzen Export abbrechen
        logger.exception("Rack-SVG für %s (%s) fehlgeschlagen", rack, face)
        return None, f"{type(e).__name__}: {e}"
