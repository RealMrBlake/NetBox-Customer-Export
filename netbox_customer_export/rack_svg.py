"""Rack-Ansichten offline (ohne HTTP-Aufruf der API) als SVG erzeugen."""
import logging

from django.utils.module_loading import import_string
from netbox.plugins import get_plugin_config

logger = logging.getLogger("netbox_customer_export")


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

            svg = RackElevationSVG(rack, user=user, include_images=False, base_url="").render(face)
        return (svg.tostring() if hasattr(svg, "tostring") else str(svg)), None
    except Exception as e:  # noqa: BLE001 – ein defektes Rack soll nicht den ganzen Export abbrechen
        logger.exception("Rack-SVG für %s (%s) fehlgeschlagen", rack, face)
        return None, f"{type(e).__name__}: {e}"
