# NetBox Customer Export

Export clear, customer-facing documentation as **PDF or Word** for a **site,
location, tenant or tenant group**.

| | |
|---|---|
| **Plugin name** | `netbox_customer_export` |
| **Package** | `netbox-customer-export` |
| **NetBox** | `4.6.8` – `4.7.x` |
| **Python** | `>=3.10` |
| **Repository** | <https://git.mrblake.cc/MrBlake/NetBox-Customer-Export> |

## Features

Before exporting, the technician selects which content the document contains:

| Group | Content |
|---|---|
| General | Overview & site data (address, location tree, key figures), contacts |
| Infrastructure | Racks by site → location with rack elevation (front/rear, optionally with device images as in NetBox) and occupancy list, devices by **selectable device roles** (servers, switches, APs, routers …) with **selectable columns**, power, VMs |
| Network | VRFs (incl. RTs), prefixes by VRF, VLANs, IP addresses (detailed), WLANs/SSIDs, circuits, **network topology** |
| Contracts & licenses | Licenses from [NetBox-SLM](https://git.mrblake.cc/MrBlake/NetBox-SLM) (detected automatically) or another license plugin (e.g. `netbox-lifecycle`) |

**IP versions** (IPv4, IPv6 or both) control which addresses appear in the
document: management/OOB IPs, VMs, topology labels, prefixes and IP addresses.

All queries respect NetBox permissions (`.restrict(user, "view")`) — a
technician only exports what they are allowed to see.

Open it via the **Customer doc** button on site, location, tenant and tenant
group pages, or via **Plugins → Customer documentation**. Output formats:
**PDF**, **Word** and **HTML preview** (opens in a new tab).

## Compatibility

- NetBox `4.6.8` – `4.7.x`
- Python `>=3.10`
- System libraries for PDF and rack graphics in Word: Pango, Cairo

## Installation

All paths assume a standard installation under `/opt/netbox`.

### 0. System libraries

Required for PDF output and rack graphics in Word:

```bash
sudo apt install -y libpango-1.0-0 libpangoft2-1.0-0 libcairo2 git
```

### 1. Install the package

```bash
/opt/netbox/venv/bin/pip install --upgrade --force-reinstall \
  "netbox-customer-export[all] @ git+https://git.mrblake.cc/MrBlake/NetBox-Customer-Export.git@main"
```

The extras control what is installed alongside:

| Extra | Packages | Formats |
|---|---|---|
| `[all]` | weasyprint, python-docx, cairosvg | PDF + Word + HTML |
| `[pdf]` | weasyprint | PDF + HTML |
| `[docx]` | python-docx, cairosvg | Word + HTML |

For reproducible production installs, replace `main` with a release tag or a
full commit ID.

### 2. Add the plugin to `local_requirements.txt`

This makes `upgrade.sh` reinstall the plugin automatically on every NetBox upgrade:

```bash
grep -qxF "netbox-customer-export[all] @ git+https://git.mrblake.cc/MrBlake/NetBox-Customer-Export.git@main" /opt/netbox/local_requirements.txt \
  || echo "netbox-customer-export[all] @ git+https://git.mrblake.cc/MrBlake/NetBox-Customer-Export.git@main" | sudo tee -a /opt/netbox/local_requirements.txt
```

If the repository is private, the NetBox server needs a read-only deploy token
or an SSH key. Do not store credentials in `local_requirements.txt`.

### 3. Enable the plugin

In `/opt/netbox/netbox/netbox/configuration.py`:

```python
PLUGINS = [
    "netbox_customer_export",
]

PLUGINS_CONFIG = {
    "netbox_customer_export": {
        "company_name": "My IT Ltd",       # branding options: see below
        "logo_path": "/opt/netbox/branding/logo.png",
        "footer_text": "Confidential",
        # Offline rack SVG from Netbox-Utilities (multiple devices per U):
        # function with signature fn(rack, face, user) -> SVG string
        "rack_svg_renderer": None,         # e.g. "netbox_utilities.<module>.<function>"
        "allow_secrets": False,            # allow exporting WLAN PSKs / license keys
        # "license_sources": [ { "model": "app.model", "device_field": "device",
        #                        "tenant_field": "tenant", "columns": [("License", "license"), ...] } ],
    },
}
```

If other plugins are already configured, add `netbox_customer_export` to the
existing list and dictionary instead of replacing them.

### 4. Apply migrations, collect static files, restart

```bash
cd /opt/netbox/netbox
/opt/netbox/venv/bin/python manage.py migrate netbox_customer_export
/opt/netbox/venv/bin/python manage.py collectstatic --no-input
/opt/netbox/venv/bin/python manage.py remove_stale_contenttypes --no-input
/opt/netbox/venv/bin/python manage.py clearsessions
sudo systemctl restart netbox netbox-rq
```

`migrate` is mandatory since version 0.2.0: it creates the tables for branding
profiles and topology symbols.

## Update

```bash
/opt/netbox/venv/bin/pip install --upgrade --force-reinstall --no-deps \
  "netbox-customer-export @ git+https://git.mrblake.cc/MrBlake/NetBox-Customer-Export.git@main"

cd /opt/netbox/netbox
/opt/netbox/venv/bin/python manage.py migrate netbox_customer_export
/opt/netbox/venv/bin/python manage.py collectstatic --no-input
sudo systemctl restart netbox netbox-rq
```

`--force-reinstall` makes pip pick up branch changes even if the package
version has not been bumped. `--no-deps` avoids reinstalling WeasyPrint & co.

When NetBox itself is upgraded, `upgrade.sh` reinstalls the plugin from
`local_requirements.txt` and runs migrations and `collectstatic`:

```bash
sudo /opt/netbox/upgrade.sh
sudo systemctl restart netbox netbox-rq
```

If you pinned a release tag in `local_requirements.txt`, change the tag there
before running the upgrade. Check first that the plugin supports the new NetBox
version (`min_version`/`max_version`), otherwise NetBox refuses to start.

Check the installed version:

```bash
/opt/netbox/venv/bin/pip show netbox-customer-export
```

## Uninstall

1. Remove `"netbox_customer_export"` from `PLUGINS` and `PLUGINS_CONFIG`.
2. Remove the line from `/opt/netbox/local_requirements.txt`.
3. Uninstall the package and restart NetBox:

```bash
/opt/netbox/venv/bin/pip uninstall netbox-customer-export
sudo sed -i '/netbox-customer-export/d' /opt/netbox/local_requirements.txt
sudo systemctl restart netbox netbox-rq
```

## Configuration

### Branding in NetBox (recommended)

Under **Plugins → Branding profiles**, admins create design profiles directly in NetBox:

- name, company name, footer and **logo upload** (PNG/JPG)
- colours via colour picker: primary, accent, table header text, labels, zebra stripes
- font family and size
- **Word template upload** (`.docx`/`.dotx`), optionally with the name of a table style
- extra CSS for PDF and HTML
- **Preview** button that opens a sample document in the selected design
- one profile can be marked as **default** and is preselected in the export form

Uploads are stored under `MEDIA_ROOT/customer-export/` (default:
`/opt/netbox/netbox/media/customer-export/`) and should be backed up. Deleting a
profile also removes its logo and template.

**Permissions:** superusers can do everything. Other users or groups need a
permission for the object type *Customer Export | Branding profile*
(*View* for list and preview; *Add*, *Change*, *Delete* to maintain profiles).
Technicians who only export need none of these.

Profiles created in NetBox appear first in the "Design / Company" selection;
profiles from `configuration.py` are offered additionally if `brandings` is defined.

### Branding via `configuration.py`

Profiles can also be defined in the configuration — globally or as **multiple
profiles** (e.g. per company or brand). Global values are the base; each
profile only overrides the values it sets.

```python
PLUGINS_CONFIG = {
    "netbox_customer_export": {
        "company_name": "My IT Ltd",   # base for all profiles
        "brandings": {
            "standard": {"name": "My IT Ltd", "logo_path": "/opt/netbox/branding/logo.png"},
            "partner": {
                "name": "Partner Inc",
                "company_name": "Partner Inc",
                "logo_path": "/opt/netbox/branding/partner.png",
                "primary_color": "#C00000",
                "accent_color": "#E46C0A",
                "font_family": "Arial",
                "docx_template": "/opt/netbox/branding/partner.dotx",
                "docx_table_style": "Grid Table 4 - Accent 1",
            },
        },
    },
}
```

| Key | Default | Effect |
|---|---|---|
| `name` | profile key | Display name in the form |
| `company_name`, `logo_path`, `footer_text` | – | Cover page and footer |
| `primary_color` | `1F4E79` | Headings, table headers |
| `accent_color` | `2E75B6` | Sub-headings (level 3/4) |
| `header_text_color` | `FFFFFF` | Table header text |
| `label_bg_color` | `DEEAF6` | Label column of detail tables |
| `stripe_color` | `F3F7FB` | Zebra stripes (PDF) |
| `font_family`, `font_size` | `Calibri`, `10` | Base font |
| `docx_template` | – | `.docx`/`.dotx`: styles, header/footer and margins are used, the template's text content is discarded |
| `docx_table_style` | – | Name of a table style from the template (as shown in Word). If set, the plugin's own colouring is skipped. |
| `extra_css` | – | Extra CSS for PDF/HTML |

Colours are hex values with or without `#`; invalid values produce a clear
error message on export. With a Word template, the template defines the heading
styles and its own footer is kept.

### Network topology

The **Network topology** section draws one diagram per site with icons in the
style of Cisco Packet Tracer:

- Links come from NetBox **cable paths**; paths through patch panels are traced to the end device.
- The top-to-bottom layout follows the cabling: provider → firewall/router → core → access → end devices, with ordering optimised for as few crossings as possible.
- Lines are routed **orthogonally** on bus bars, coloured per upstream device. Port names sit at the target device; multiple uplinks are drawn thicker and marked "2×".
- **Scope**: *entire network* (one page per site) and/or *per rack* (one page per rack). In the rack view, directly connected devices outside the rack appear faded and dashed, with their rack.
- Each topology gets its **own landscape page** (PDF and Word) and is scaled as large as possible.
- Provider circuits appear as a cloud, devices of other sites dashed (can be disabled).
- Selectable labels: management IP, model, ports on links.
- Device names longer than 15 characters are wrapped, preferably at `-`, `_`, `.` or spaces.

**Symbols** (menu **Plugins → Topology symbols**, or the "Topology symbol"
button on device type and device role pages):

1. per **device type**: choose a built-in symbol or **upload a custom icon** (PNG/JPG, ideally transparent)
2. per **device role**
3. otherwise **automatic**, first by role, then by model and manufacturer

Built-in symbols: internet/provider, modem/NTU, firewall, router, layer-3
switch, switch, radio link, WLAN controller, PoE injector, access point, server,
storage/SAN, NAS, tape library, UPS/ATS, PBX, IP phone, PC/client, printer,
camera and "other".

Patch panels, power strips, PDUs, cable management and rooms are hidden
automatically; further device types or roles can be hidden via "Hide in
topology". Custom icons are stored under `MEDIA_ROOT/customer-export/symbols/`.
Permissions: object type *Customer Export | Topology symbol*, analogous to
branding profiles.

### Licenses (NetBox-SLM)

If [NetBox-SLM](https://git.mrblake.cc/MrBlake/NetBox-SLM) is installed, the
**Licenses** section reads its software licenses automatically — no
configuration required. A license belongs to the export if

- its **installation** is on a device, VM or cluster in the selected site/location/tenant, or
- it is assigned to the exported **tenant**, or
- it has no tenant but is assigned to a **tenant group** the tenant belongs to (including parent groups), or that lies within the exported tenant group.

Tables are grouped by manufacturer and show license, product/version, type,
quantity, term (incl. renewal), status (*active*, *expires in N days* from 90
days before expiry, *expired*, *perpetual*), support, installation and tenant.
The **license key** only appears with the "Export secrets" option (requires
`allow_secrets: True`). Additionally configured `license_sources` are still output.

### Rack elevations

By default the plugin uses NetBox's own `dcim.svg.RackElevationSVG` in-process
(no HTTP call to the API). To use the offline renderer from
[Netbox-Utilities](https://git.mrblake.cc/MrBlake/Netbox-Utilities) instead,
set `rack_svg_renderer` to the path of its render function. A small adapter is
needed if the signature differs.

## Architecture

```
scope.py        which objects belong to the scope (site/location/tenant/group)
sections.py     registry of sections (@section decorator) → neutral blocks
blocks.py       document model (heading, table, key/value, images, page break)
renderers/      html (→ WeasyPrint PDF), docx (python-docx + cairosvg)
```

To add a section, write a function in `sections.py` decorated with
`@section("key", "Label", "Group")` that returns a list of blocks. It appears
automatically in the form and in both output formats.

## License

Apache License 2.0.
