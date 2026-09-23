"""Rack-Ansichten offline (ohne HTTP-Aufruf der API) als SVG erzeugen."""
import logging

from django.utils.module_loading import import_string
from netbox.plugins import get_plugin_config

logger = logging.getLogger("netbox_customer_export")

# NetBox-Standardwerte der Rack-Ansicht
UNIT_WIDTH = 220
UNIT_HEIGHT = 22
LEGEND_WIDTH = 30
MARGIN_WIDTH = 15


def render_rack_svg(rack, face, user):
    """Gibt (svg, fehler) zurück – genau einer der beiden Werte ist None.

    Ist ``rack_svg_renderer`` gesetzt (z.B. der Offline-Renderer aus Netbox-Utilities, der mehrere
    Geräte pro HE korrekt darstellt), wird dieser aufgerufen: ``fn(rack=..., face=..., user=...)``.
    Andernfalls wird NetBox' eigener RackElevationSVG direkt in-process genutzt.
    """
    try:
        renderer = get_plugin_config("netbox_customer_export", "rack_svg_renderer")
        if renderer:
            svg = import_string(renderer)(rack=rack, face=face, user=user)
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
                include_images=False,
                base_url="",
            ).render(face)
        return (svg.tostring() if hasattr(svg, "tostring") else str(svg)), None
    except Exception as e:  # noqa: BLE001 – ein defektes Rack soll nicht den ganzen Export abbrechen
        logger.exception("Rack-SVG für %s (%s) fehlgeschlagen", rack, face)
        return None, f"{type(e).__name__}: {e}"
