# NetBox Customer Export

NetBox-Plugin (4.6.8 – 4.7.99) zum Export einer verständlichen **Kundendokumentation als PDF oder Word**
für einen **Standort, eine Lokation, einen Mandanten oder eine Mandantengruppe**.

Der Techniker wählt vor dem Export aus, welche Inhalte das Dokument enthalten soll:

| Gruppe | Inhalte |
|---|---|
| Allgemein | Übersicht & Standortdaten (Adresse, Lokationsbaum, Kennzahlen), Ansprechpartner |
| Infrastruktur | Racks nach Standort → Lokation mit Rack-Ansicht (Vorder-/Rückseite, optional mit Gerätebildern wie in NetBox) und Belegungsliste, Geräte nach **frei wählbaren Geräterollen** (Server, Switche, APs, Router …) mit **frei wählbaren Spalten**, Stromversorgung, VMs |
| Netzwerk | VRFs (inkl. RTs), Präfixe nach VRF, VLANs, IP-Adressen (ausführlich), WLANs/SSIDs, Leitungen, **Netzwerk-Topologie** |
| Verträge & Lizenzen | Lizenzen aus einem Lizenz-Plugin (Standard: `netbox-lifecycle`) |

Alle Abfragen laufen über die NetBox-Berechtigungen (`.restrict(user, "view")`). Ein Techniker exportiert also nur, was er auch sehen darf.

## Aufruf

* Button **„Kundendoku“** auf Standort-, Lokations-, Mandanten- und Mandantengruppen-Seiten
* oder Menü **Plugins → Kundendokumentation**

Formate: **PDF**, **Word** und **HTML-Vorschau** (öffnet in neuem Tab).

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

`migrate` ist ab Version 0.2.0 **Pflicht**, denn es legt die Tabellen für Branding-Profile und (ab 0.4.0) Topologie-Symbole an. Die übrigen Befehle gehören zum
üblichen NetBox-Ablauf nach jeder Plugin-Installation.

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
Vorher prüfen, ob die Plugin-Version die neue NetBox-Version unterstützt (`min_version`/`max_version`, aktuell 4.6.8 – 4.7.99).
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

### Design / Branding in NetBox (empfohlen)

Unter **Plugins → Branding-Profile** legen Admins Design-Profile direkt in NetBox an:

* Name, Firmenname, Fußzeile und **Logo-Upload** (PNG/JPG)
* Farben per Farbwähler: Primär, Akzent, Tabellenkopf-Schrift, Beschriftungen, Zebrastreifen
* Schriftart und -größe
* **Upload einer Word-Vorlage** (.docx/.dotx), optional mit dem Namen einer Tabellenformatvorlage
* zusätzliches CSS für PDF und HTML
* **Vorschau**-Button, der ein Beispieldokument im gewählten Design öffnet
* Ein Profil lässt sich als **Standard** markieren und ist dann im Exportformular vorausgewählt.

Uploads landen unter `MEDIA_ROOT/customer-export/` (Standard: `/opt/netbox/netbox/media/customer-export/`) und sollten mitgesichert werden.
Beim Löschen eines Profils werden Logo und Vorlage mit entfernt.

**Berechtigungen:** Superuser dürfen alles. Anderen Benutzern oder Gruppen weist man unter *Admin → Berechtigungen* eine
Berechtigung für den Objekttyp *Customer Export | Branding-Profil* zu. Mit *Ansehen* sieht man Liste und Vorschau, zum Pflegen
braucht es zusätzlich *Hinzufügen*, *Ändern* und *Löschen*. Techniker, die nur exportieren, benötigen keine davon.

Sind in NetBox Profile angelegt, erscheinen sie zuerst in der Auswahl „Design / Firma“. Profile aus `configuration.py`
(siehe unten) werden zusätzlich angeboten, wenn dort `brandings` definiert ist.

### Design / Branding per `configuration.py`

Alternativ oder ergänzend lassen sich Profile in der Konfiguration festlegen, entweder global oder als **mehrere Profile**
(z.B. pro eigener Firma oder Marke). Die globalen Werte gelten als Basis, jedes Profil überschreibt nur die Werte, die es selbst setzt.

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

### Netzwerk-Topologie

Der Abschnitt **Netzwerk-Topologie** zeichnet je Standort ein Diagramm mit Symbolen im Stil von Cisco Packet Tracer:

* Verbindungen stammen aus den **Kabelpfaden** in NetBox. Pfade über Patchpanels werden bis zum Endgerät verfolgt.
* Die Anordnung von oben nach unten ergibt sich aus der Verkabelung: Provider → Firewall/Router → Core → Access → Endgeräte.
  Die Reihenfolge innerhalb einer Ebene wird so optimiert, dass sich möglichst wenige Leitungen kreuzen.
* Leitungen werden **rechtwinklig** über eigene Sammelschienen geführt, farbig je übergeordnetem Gerät. Portnamen stehen
  direkt am Zielgerät, Mehrfach-Uplinks werden dicker gezeichnet und als „2×“ markiert.
* Jede Topologie steht auf einer **eigenen Seite im Querformat** (PDF und Word) und wird so groß wie möglich skaliert.
  Danach geht das Dokument im Hochformat weiter.
* Provider-Leitungen erscheinen als Wolke, Geräte anderer Standorte gestrichelt (abschaltbar).
* Beschriftung wählbar: Management-IP, Modell, Ports an den Verbindungen.

**Symbole** (Menü **Plugins → Topologie-Symbole**, oder Button „Topologie-Symbol“ auf Gerätetyp- und Geräterollen-Seiten):

1. Zuordnung je **Gerätetyp**: eingebautes Symbol wählen oder **eigenes Icon hochladen** (PNG/JPG, idealerweise transparent)
2. Zuordnung je **Geräterolle**
3. sonst **automatisch**, zuerst anhand der Rolle, dann anhand von Modell und Hersteller

Eingebaute Symbole: Internet/Provider, Modem/NTU/RAD, Firewall, Router, Layer-3-Switch, Switch, Funkstrecke,
WLAN-Controller, PoE-Injektor, Access Point, Server, Storage/SAN (MSA), NAS, Bandlaufwerk/Tape Library, USV/ATS,
Telefonanlage, IP-Telefon, PC/Client, Drucker, Kamera und „Sonstiges“.

Patchpanels, Steckdosen(leisten), PDUs, Kabelmanagement und Räume werden automatisch ausgeblendet. Über „In Topologie ausblenden“ lassen sich
weitere Gerätetypen oder Rollen ausblenden. Eigene Icons liegen unter `MEDIA_ROOT/customer-export/symbols/`.
Berechtigungen: Objekttyp *Customer Export | Topologie-Symbol*, analog zu den Branding-Profilen.

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
