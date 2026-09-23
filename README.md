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

Die Pfade gehen von einer Standardinstallation unter `/opt/netbox` aus.

### 1. Systembibliotheken (für PDF und Rack-Grafiken in Word)

```bash
sudo apt install -y libpango-1.0-0 libpangoft2-1.0-0 libcairo2 git
```

### 2. Plugin per Git installieren

```bash
source /opt/netbox/venv/bin/activate
pip install "netbox-customer-export[all] @ git+https://git.mrblake.cc/MrBlake/NetBox-Customer-Export.git"
```

Die Extras regeln, was mitinstalliert wird:

| Extra | Pakete | Formate |
|---|---|---|
| `[all]` | weasyprint, python-docx, cairosvg | PDF + Word + HTML |
| `[pdf]` | weasyprint | PDF + HTML |
| `[docx]` | python-docx, cairosvg | Word + HTML |

Eine bestimmte Version (Tag oder Commit) installierst du mit `@<tag>` hinter der URL, z.B.
`git+https://git.mrblake.cc/MrBlake/NetBox-Customer-Export.git@v0.1.0`.

### 3. In `local_requirements.txt` aufnehmen

NetBox' `upgrade.sh` legt das venv bei jedem NetBox-Update neu an. Nur Pakete aus `local_requirements.txt` werden danach
automatisch wieder installiert. Deshalb das Plugin dort eintragen:

```bash
echo 'netbox-customer-export[all] @ git+https://git.mrblake.cc/MrBlake/NetBox-Customer-Export.git' \
  | sudo tee -a /opt/netbox/local_requirements.txt
```

Soll eine feste Version eingespielt werden, trägst du dort ebenfalls `@<tag>` ein.

### 4. In `configuration.py` aktivieren

`/opt/netbox/netbox/netbox/configuration.py`:

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

### 5. Migrationen, statische Dateien, Neustart

```bash
source /opt/netbox/venv/bin/activate
cd /opt/netbox/netbox
python3 manage.py migrate
python3 manage.py collectstatic --no-input
python3 manage.py remove_stale_contenttypes --no-input
python3 manage.py clearsessions
sudo systemctl restart netbox netbox-rq
```

Die Befehle gehören zum üblichen NetBox-Ablauf nach jeder Plugin-Installation und laufen auch dann fehlerfrei, wenn es nichts zu tun gibt.
Die aktuelle Version hat noch keine eigenen Datenbanktabellen und keine statischen Dateien. Spätere Versionen können sie aber mitbringen.

## Update

```bash
source /opt/netbox/venv/bin/activate
pip install --upgrade --force-reinstall --no-deps "netbox-customer-export @ git+https://git.mrblake.cc/MrBlake/NetBox-Customer-Export.git"
```

Danach wie bei der Installation:

```bash
source /opt/netbox/venv/bin/activate
cd /opt/netbox/netbox
python3 manage.py migrate
python3 manage.py collectstatic --no-input
python3 manage.py remove_stale_contenttypes --no-input
python3 manage.py clearsessions
sudo systemctl restart netbox netbox-rq
```

`--force-reinstall` ist nötig, weil pip ein Git-Paket mit unveränderter Versionsnummer sonst nicht neu holt.
`--no-deps` verhindert, dass dabei auch WeasyPrint & Co. neu installiert werden. Bei einer festen Version in
`local_requirements.txt` dort den Tag anpassen und denselben Befehl mit `@<neuer-tag>` ausführen.

Installierte Version prüfen:

```bash
pip show netbox-customer-export
```

### NetBox-Update

Beim NetBox-Update installiert `sudo /opt/netbox/upgrade.sh` das Plugin automatisch aus `local_requirements.txt` neu.
Vorher prüfen, ob die Plugin-Version die neue NetBox-Version unterstützt (`min_version`/`max_version`, aktuell 4.6.8 – 4.6.99).
Andernfalls verweigert NetBox den Start.

## Deinstallation

```bash
# "netbox_customer_export" aus PLUGINS in configuration.py entfernen, dann:
source /opt/netbox/venv/bin/activate
pip uninstall netbox-customer-export
sudo sed -i '/netbox-customer-export/d' /opt/netbox/local_requirements.txt
sudo systemctl restart netbox netbox-rq
```

## Konfiguration

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
