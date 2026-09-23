"""Branding-Profile (Logo, Farben, Schrift, Word-Vorlage) aus PLUGINS_CONFIG."""
import re

from netbox.plugins import get_plugin_config

PLUGIN = "netbox_customer_export"

DEFAULT_BRANDING = {
    "name": "Standard",
    "company_name": "",
    "logo_path": None,
    "footer_text": "Vertraulich – nur für den internen Gebrauch des Kunden",
    "primary_color": "1F4E79",  # Überschriften, Tabellenköpfe
    "accent_color": "2E75B6",  # Unterüberschriften
    "header_text_color": "FFFFFF",  # Schrift im Tabellenkopf
    "label_bg_color": "DEEAF6",  # Beschriftungsspalte in Key/Value-Tabellen
    "stripe_color": "F3F7FB",  # jede zweite Tabellenzeile (PDF)
    "font_family": "Calibri",
    "font_size": 10,
    # Word: .docx/.dotx, deren Formatvorlagen, Kopf-/Fußzeile und Seitenränder übernommen werden
    "docx_template": None,
    "docx_table_style": None,  # z.B. "Gitternetztabelle 4 – Akzent 1" aus der Vorlage
    "extra_css": "",  # zusätzliches CSS für PDF/HTML
}

COLOR_KEYS = ("primary_color", "accent_color", "header_text_color", "label_bg_color", "stripe_color")
_HEX = re.compile(r"^[0-9A-Fa-f]{6}$")


def _normalize(profile):
    for key in COLOR_KEYS:
        value = str(profile[key]).lstrip("#")
        if not _HEX.match(value):
            raise ValueError(f"netbox_customer_export: {key}={profile[key]!r} ist keine Hex-Farbe (z.B. '1F4E79')")
        profile[key] = value.upper()
    return profile


def get_brandings():
    """Alle Profile als {key: dict}. Top-Level-Einstellungen gelten als Basis für jedes Profil."""
    base = dict(DEFAULT_BRANDING)
    for key in DEFAULT_BRANDING:
        value = get_plugin_config(PLUGIN, key)
        if value is not None:
            base[key] = value
    profiles = get_plugin_config(PLUGIN, "brandings") or {}
    if not profiles:
        return {"default": _normalize(base)}
    return {key: _normalize({**base, "name": key, **profile}) for key, profile in profiles.items()}


def get_branding(key=None):
    brandings = get_brandings()
    return brandings.get(key) or next(iter(brandings.values()))
