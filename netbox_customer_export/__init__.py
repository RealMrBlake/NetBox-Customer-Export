from netbox.plugins import PluginConfig


class CustomerExportConfig(PluginConfig):
    name = "netbox_customer_export"
    verbose_name = "Kunden-Export"
    description = "Kundendokumentation als PDF oder Word exportieren"
    version = "0.5.0"
    author = "Claude"
    base_url = "customer-export"
    min_version = "4.6.8"
    max_version = "4.7.99"
    default_settings = {
        # Branding: Einzelschlüssel (company_name, logo_path, primary_color, docx_template, …)
        # gelten global; "brandings" definiert mehrere Profile. Defaults siehe branding.py.
        "brandings": None,
        # Dotted path zu einer Funktion fn(rack, face, user) -> SVG-String,
        # z.B. der Offline-Renderer aus Netbox-Utilities. None = NetBox-eigener Renderer.
        "rack_svg_renderer": None,
        # Lizenzquellen (Plugin-Modelle), None = Auto-Erkennung (netbox_lifecycle)
        "license_sources": None,
        # Darf der Techniker WLAN-PSKs o.ä. mit exportieren?
        "allow_secrets": False,
    }


config = CustomerExportConfig
