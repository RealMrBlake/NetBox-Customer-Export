# NetBox Customer Export

NetBox-Plugin (4.6.8 – 4.6.99) zum Export einer verständlichen **Kundendokumentation als PDF oder Word**
für einen **Standort, eine Lokation, einen Mandanten oder eine Mandantengruppe**.

Der Techniker wählt vor dem Export aus, welche Inhalte das Dokument enthalten soll:

| Gruppe | Inhalte |
|---|---|
| Allgemein | Übersicht & Standortdaten (Adresse, Lokationsbaum, Kennzahlen), Ansprechpartner |
| Infrastruktur | Racks nach Standort → Lokation mit Rack-Ansicht (SVG, Vorder-/Rückseite) und Belegungsliste, Geräte nach **frei wählbaren Geräterollen** (Server, Switche, APs, Router …) mit **frei wählbaren Spalten**, Stromversorgung, VMs |
| Netzwerk | VRFs (inkl. RTs), Präfixe nach VRF, VLANs, IP-Adressen (ausführlich), WLANs/SSIDs, Leitungen |
| Verträge & Lizenzen | Lizenzen aus einem Lizenz-Plugin (Standard: `netbox-lifecycle`) |

Alle Abfragen laufen über die NetBox-Berechtigungen (`.restrict(user, "view")`). Ein Techniker exportiert also nur, was er auch sehen darf.

## Aufruf

* Button **„Kundendoku“** auf Standort-, Lokations-, Mandanten- und Mandantengruppen-Seiten
* oder Menü **Plugins → Kundendokumentation**

## Installation

```bash
source /opt/netbox/venv/bin/activate
pip install "netbox-customer-export[all] @ git+https://<dein-git>/NetBox-Customer-Export.git"
# WeasyPrint/cairosvg benötigen Systembibliotheken:
sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libcairo2
```

In `local_requirements.txt` eintragen, damit das Plugin NetBox-Upgrades übersteht.

`configuration.py`:

```python
PLUGINS = ["netbox_customer_export"]
PLUGINS_CONFIG = {
    "netbox_customer_export": {
        "company_name": "Meine IT GmbH",  # Branding-Optionen siehe unten
        "logo_path": "/opt/netbox/branding/logo.png",
        "footer_text": "Vertraulich",
        # Offline-Rack-SVG aus Netbox-Utilities (mehrere Geräte pro HE):
        # Funktion mit Signatur fn(rack, face, user) -> SVG-String
        "rack_svg_renderer": None,   # z.B. "netbox_utilities.<modul>.<funktion>"
        "allow_secrets": False,      # WLAN-PSK-Export erlauben
        # "license_sources": [ { "model": "app.model", "device_field": "device",
        #                        "tenant_field": "tenant", "columns": [("Lizenz", "license"), ...] } ],
    }
}
```

Danach `systemctl restart netbox`.

### Design / Branding

Farben, Schrift, Logo und eine Word-Vorlage lassen sich festlegen, entweder global oder als **mehrere Profile**
(z.B. pro eigener Firma oder Marke). Bei mehr als einem Profil erscheint im Exportformular das Auswahlfeld „Design / Firma“.
Die globalen Werte gelten als Basis, jedes Profil überschreibt nur die Werte, die es selbst setzt.

```python
PLUGINS_CONFIG = {
    "netbox_customer_export": {
        "company_name": "Meine IT GmbH",   # Basis für alle Profile
        "brandings": {
            "standard": {"name": "Meine IT GmbH", "logo_path": "/opt/netbox/branding/logo.png"},
            "partner": {
                "name": "Partner AG",
                "company_name": "Partner AG",
                "logo_path": "/opt/netbox/branding/partner.png",
                "primary_color": "#C00000",
                "accent_color": "#E46C0A",
                "font_family": "Arial",
                "docx_template": "/opt/netbox/branding/partner.dotx",
                "docx_table_style": "Gitternetztabelle 4 – Akzent 1",
            },
        },
    }
}
```

| Schlüssel | Standard | Wirkung |
|---|---|---|
| `name` | Profilschlüssel | Anzeigename im Formular |
| `company_name`, `logo_path`, `footer_text` | – | Deckblatt und Fußzeile |
| `primary_color` | `1F4E79` | Überschriften, Tabellenköpfe |
| `accent_color` | `2E75B6` | Unterüberschriften (Ebene 3/4) |
| `header_text_color` | `FFFFFF` | Schrift im Tabellenkopf |
| `label_bg_color` | `DEEAF6` | Beschriftungsspalte der Detailtabellen |
| `stripe_color` | `F3F7FB` | Zebrastreifen (PDF) |
| `font_family`, `font_size` | `Calibri`, `10` | Grundschrift |
| `docx_template` | – | `.docx`/`.dotx`: Formatvorlagen, Kopf-/Fußzeile und Ränder werden übernommen, der Textinhalt der Vorlage wird verworfen |
| `docx_table_style` | – | Name einer Tabellenformatvorlage aus der Vorlage (so, wie er in Word angezeigt wird). Ist er gesetzt, entfällt die eigene Einfärbung. |
| `extra_css` | – | zusätzliches CSS für PDF/HTML |

Farben werden als Hex angegeben, mit oder ohne `#`. Ungültige Werte führen beim Export zu einer klaren Fehlermeldung.
Mit einer Word-Vorlage bestimmt die Vorlage die Überschriften-Formate. Ohne Vorlage färbt das Plugin die Überschriften selbst ein.
Bringt die Vorlage eine eigene Fußzeile mit, wird diese beibehalten.

### Rack-Ansichten

Ohne Konfiguration nutzt das Plugin NetBox' eigenen `dcim.svg.RackElevationSVG`. Er läuft im selben Prozess, also ohne HTTP-Aufruf der API.
Soll stattdessen der Offline-Renderer aus [Netbox-Utilities](https://git.mrblake.cc/MrBlake/Netbox-Utilities) verwendet werden,
trägt man unter `rack_svg_renderer` den Pfad zu dessen Render-Funktion ein. Falls die Signatur abweicht, braucht es einen kleinen Adapter.

## Architektur

```
scope.py        welche Objekte gehören zum Scope (Standort/Lokation/Mandant/-gruppe)
sections.py     Registry der Abschnitte (@section-Dekorator) → neutrale Blöcke
blocks.py       Dokumentmodell (Überschrift, Tabelle, Key/Value, Bilder, Umbruch)
renderers/      html (→ WeasyPrint-PDF), docx (python-docx + cairosvg)
```

Einen neuen Abschnitt hinzufügen: in `sections.py` eine Funktion mit `@section("key", "Label", "Gruppe")` schreiben, die eine Liste von Blöcken zurückgibt. Er erscheint automatisch im Formular und in beiden Formaten.
