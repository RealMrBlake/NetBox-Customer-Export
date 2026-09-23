"""Registry der auswählbaren Dokumentabschnitte."""
from collections import OrderedDict
from dataclasses import dataclass
from itertools import groupby

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from netbox.plugins import get_plugin_config

from .blocks import EMPTY, H, IMAGES, KV, LANDSCAPE, P, PAGEBREAK, T, get
from .rack_png import render_rack_png
from .rack_svg import render_rack_svg


@dataclass
class Section:
    key: str
    label: str
    group: str
    default: bool
    func: callable
    hint: str = ""


SECTIONS = OrderedDict()


def section(key, label, group, default=True, hint=""):
    def deco(func):
        SECTIONS[key] = Section(key, label, group, default, func, hint)
        return func

    return deco


# --- Gerätespalten (vom Techniker wählbar) ------------------------------------

def _rack_pos(d):
    if not d.rack:
        return None
    pos = f" / HE {d.position:g}" if d.position else ""
    return f"{d.rack}{pos}"


DEVICE_COLUMNS = OrderedDict(
    [
        ("name", ("Name", lambda d: d.name or str(d))),
        ("model", ("Hersteller / Modell", lambda d: f"{d.device_type.manufacturer} {d.device_type.model}")),
        ("site", ("Standort", lambda d: d.site)),
        ("location", ("Lokation", lambda d: d.location)),
        ("rack", ("Rack / HE", _rack_pos)),
        ("status", ("Status", lambda d: d.get_status_display())),
        ("platform", ("Plattform / OS", lambda d: d.platform)),
        ("primary_ip", ("Management-IP", lambda d: d.primary_ip.address if d.primary_ip else None)),
        ("oob_ip", ("OOB-IP", lambda d: d.oob_ip.address if d.oob_ip else None)),
        ("serial", ("Seriennummer", lambda d: d.serial)),
        ("asset_tag", ("Inventarnr.", lambda d: d.asset_tag)),
        ("tenant", ("Mandant", lambda d: d.tenant)),
        ("description", ("Beschreibung", lambda d: d.description)),
    ]
)
DEFAULT_DEVICE_COLUMNS = ["name", "model", "location", "rack", "primary_ip", "serial"]


def _device_table(devices, columns):
    cols = [DEVICE_COLUMNS[c] for c in columns if c in DEVICE_COLUMNS]
    return T([c[0] for c in cols], [[c[1](d) for c in cols] for d in devices])


def _empty(opts, blocks, text="Keine Einträge vorhanden."):
    if opts.get("include_empty"):
        blocks.append(P(text))
        return blocks
    return []


# --- Abschnitte -------------------------------------------------------------

@section("overview", "Übersicht & Standortdaten", "Allgemein", hint="Kennzahlen, Adressen, Lokationsbaum")
def overview(scope, opts):
    blocks = [H(1, "Übersicht")]
    counts = [
        ("Standorte", scope.sites().count()),
        ("Racks", scope.racks().count()),
        ("Geräte", scope.devices().count()),
        ("Virtuelle Maschinen", scope.virtual_machines().count()),
        ("Präfixe", scope.prefixes().count()),
        ("VLANs", scope.vlans().count()),
        ("Leitungen", scope.circuits().count()),
    ]
    blocks.append(KV([(f"{scope.label}", scope.obj)] + counts))
    if getattr(scope.obj, "description", ""):
        blocks.append(P(scope.obj.description))

    for site in scope.sites().select_related("region", "group", "tenant"):
        blocks.append(H(2, f"Standort {site.name}"))
        blocks.append(
            KV(
                [
                    ("Status", site.get_status_display()),
                    ("Region", site.region),
                    ("Mandant", site.tenant),
                    ("Einrichtung", site.facility),
                    ("Anschrift", site.physical_address),
                    ("Lieferanschrift", site.shipping_address),
                    ("Zeitzone", site.time_zone),
                    ("Beschreibung", site.description),
                ]
            )
        )
        locs = scope.location_objects().filter(site=site)
        if locs.exists():
            blocks.append(
                T(
                    ["Lokation", "Übergeordnet", "Status", "Beschreibung"],
                    [[("  " * loc.level) + loc.name, loc.parent, loc.get_status_display(), loc.description] for loc in locs],
                )
            )
    return blocks


@section("contacts", "Ansprechpartner", "Allgemein", hint="Kontakte an Standorten, Lokationen, Mandanten")
def contacts(scope, opts):
    ContactAssignment = apps.get_model("tenancy", "ContactAssignment")
    targets = [
        (scope.sites(), "Standort"),
        (scope.location_objects(), "Lokation"),
        (scope.tenant_objects(), "Mandant"),
    ]
    rows = []
    for qs, label in targets:
        ct = ContentType.objects.get_for_model(qs.model)
        assignments = scope.restrict(
            ContactAssignment.objects.filter(object_type=ct, object_id__in=qs.values("pk"))
        ).select_related("contact", "role")
        for a in assignments:
            rows.append(
                [f"{label}: {a.object}", a.contact.name, a.role, a.get_priority_display(), a.contact.phone, a.contact.email]
            )
    blocks = [H(1, "Ansprechpartner")]
    if not rows:
        return _empty(opts, blocks)
    blocks.append(T(["Zuordnung", "Name", "Rolle", "Priorität", "Telefon", "E-Mail"], rows))
    return blocks


@section("racks", "Racks", "Infrastruktur", hint="Nach Standort & Lokation, mit Rack-Ansicht")
def racks(scope, opts):
    qs = (
        scope.racks()
        .select_related("site", "location", "role", "tenant", "rack_type")
        .order_by("site__name", "location__name", "name")
    )
    blocks = [H(1, "Racks")]
    if not qs.exists():
        return _empty(opts, blocks)
    for site, site_racks in groupby(qs, key=lambda r: r.site):
        blocks.append(H(2, f"Standort {site}"))
        for location, loc_racks in groupby(site_racks, key=lambda r: r.location):
            blocks.append(H(3, f"Lokation {location}" if location else "Ohne Lokation"))
            for rack in loc_racks:
                blocks.append(H(4, f"Rack {rack.name}"))
                blocks.append(
                    KV(
                        [
                            ("Status", rack.get_status_display()),
                            ("Rolle", rack.role),
                            ("Typ", rack.rack_type),
                            ("Höhe", f"{rack.u_height} HE"),
                            ("Facility-ID", rack.facility_id),
                            ("Mandant", rack.tenant),
                            ("Beschreibung", rack.description),
                        ]
                    )
                )
                if opts.get("rack_svg"):
                    images, errors = [], []
                    rack_devs = list(
                        scope.restrict(rack.devices.all()).select_related("device_type", "role")
                    )
                    with_images = bool(opts.get("rack_images"))
                    for face in opts.get("rack_faces") or ["front"]:
                        caption = "Vorderseite" if face == "front" else "Rückseite"
                        svg, svg_error = render_rack_svg(rack, face, scope.user, images=with_images, devices=rack_devs)
                        png = None
                        # PNG wird für Word gebraucht (falls kein cairosvg) und ersetzt ein fehlgeschlagenes SVG
                        if opts.get("format") == "docx" or not svg:
                            try:
                                png = render_rack_png(rack, face, rack_devs, images=with_images)
                            except Exception as e:  # noqa: BLE001
                                svg_error = f"{svg_error or ''} / PNG: {type(e).__name__}: {e}".strip(" /")
                        if svg or png:
                            images.append((svg, caption, png))
                        else:
                            errors.append(f"Rack-Ansicht ({caption}) konnte nicht erzeugt werden: {svg_error}")
                    if images:
                        blocks.append(IMAGES(images))
                    blocks += [P(e) for e in errors]
                if opts.get("rack_devices"):
                    devs = scope.restrict(rack.devices.all()).select_related("device_type__manufacturer").order_by("-position", "name")
                    if devs.exists():
                        blocks.append(
                            T(
                                ["HE", "Gerät", "Hersteller / Modell", "Seite"],
                                [
                                    [f"{d.position:g}" if d.position else EMPTY, d.name, f"{d.device_type.manufacturer} {d.device_type.model}", d.get_face_display() if d.face else EMPTY]
                                    for d in devs
                                ],
                            )
                        )
                if opts.get("rack_pagebreak"):
                    blocks.append(PAGEBREAK())
    return blocks


@section("devices", "Geräte", "Infrastruktur", hint="Tabellen je Geräterolle")
def devices(scope, opts):
    blocks = [H(1, "Geräte")]
    base = scope.devices().select_related(
        "device_type__manufacturer", "role", "site", "location", "rack", "platform", "primary_ip4", "primary_ip6", "oob_ip", "tenant"
    )
    columns = opts.get("device_columns") or DEFAULT_DEVICE_COLUMNS
    found = False
    for role in opts.get("roles") or []:
        devs = base.filter(role=role).order_by("site__name", "location__name", "rack__name", "-position", "name")
        if not devs.exists():
            continue
        found = True
        blocks.append(H(2, role.name))
        if opts.get("group_by_site"):
            for site, site_devs in groupby(devs, key=lambda d: d.site):
                blocks.append(H(3, f"Standort {site}"))
                blocks.append(_device_table(list(site_devs), columns))
        else:
            blocks.append(_device_table(devs, columns))
    return blocks if found else _empty(opts, blocks)


@section("power", "Stromversorgung", "Infrastruktur", default=False, hint="Power Panels & Feeds")
def power(scope, opts):
    qs = scope.power_feeds().select_related("power_panel", "rack").order_by("power_panel__name", "name")
    blocks = [H(1, "Stromversorgung")]
    if not qs.exists():
        return _empty(opts, blocks)
    blocks.append(
        T(
            ["Panel", "Feed", "Rack", "Status", "Typ", "Phase", "Spannung", "Ampere"],
            [[f.power_panel, f.name, f.rack, get(f, "status"), get(f, "type"), get(f, "phase"), f"{f.voltage} V", f"{f.amperage} A"] for f in qs],
        )
    )
    return blocks


@section("vms", "Virtuelle Maschinen", "Infrastruktur", default=False, hint="Cluster, Ressourcen, IP")
def vms(scope, opts):
    qs = scope.virtual_machines().select_related("cluster", "role", "platform", "primary_ip4", "primary_ip6").order_by("cluster__name", "name")
    blocks = [H(1, "Virtuelle Maschinen")]
    if not qs.exists():
        return _empty(opts, blocks)
    blocks.append(
        T(
            ["Name", "Cluster", "Rolle", "Status", "OS", "vCPU", "RAM (MB)", "Disk (MB)", "IP"],
            [[vm.name, vm.cluster, vm.role, get(vm, "status"), vm.platform, vm.vcpus, vm.memory, vm.disk, vm.primary_ip.address if vm.primary_ip else None] for vm in qs],
        )
    )
    return blocks


@section("vrfs", "VRFs", "Netzwerk", hint="Inkl. Route Targets")
def vrfs(scope, opts):
    qs = scope.vrfs().select_related("tenant").prefetch_related("import_targets", "export_targets").order_by("name")
    blocks = [H(1, "VRFs")]
    if not qs.exists():
        return _empty(opts, blocks)
    blocks.append(
        T(
            ["Name", "RD", "Mandant", "Import-RT", "Export-RT", "Beschreibung"],
            [[v.name, v.rd, v.tenant, v.import_targets, v.export_targets, v.description] for v in qs],
        )
    )
    return blocks


@section("prefixes", "IP-Netze", "Netzwerk", hint="Präfixe gruppiert nach VRF")
def prefixes(scope, opts):
    qs = scope.prefixes().select_related("vrf", "vlan", "role", "tenant").order_by("vrf__name", "prefix")
    blocks = [H(1, "IP-Netze")]
    if not qs.exists():
        return _empty(opts, blocks)
    for vrf, items in groupby(qs, key=lambda p: p.vrf):
        blocks.append(H(2, f"VRF {vrf}" if vrf else "Global"))
        blocks.append(
            T(
                ["Präfix", "VLAN", "Rolle", "Status", "Scope", "Beschreibung"],
                [[p.prefix, p.vlan, p.role, get(p, "status"), p.scope, p.description] for p in items],
            )
        )
    return blocks


@section("vlans", "VLANs", "Netzwerk", hint="VID, Name, Gruppe, Rolle")
def vlans(scope, opts):
    qs = scope.vlans().select_related("group", "site", "role", "tenant").order_by("group__name", "vid")
    blocks = [H(1, "VLANs")]
    if not qs.exists():
        return _empty(opts, blocks)
    blocks.append(
        T(
            ["VID", "Name", "Gruppe", "Standort", "Rolle", "Status", "Beschreibung"],
            [[v.vid, v.name, v.group, v.site, v.role, get(v, "status"), v.description] for v in qs],
        )
    )
    return blocks


@section("ips", "IP-Adressen", "Netzwerk", default=False, hint="Ausführlich – kann lang werden")
def ips(scope, opts):
    qs = scope.ip_addresses().select_related("vrf", "tenant").prefetch_related("assigned_object").order_by("vrf__name", "address")
    blocks = [H(1, "IP-Adressen")]
    if not qs.exists():
        return _empty(opts, blocks)
    for vrf, items in groupby(qs, key=lambda i: i.vrf):
        blocks.append(H(2, f"VRF {vrf}" if vrf else "Global"))
        rows = []
        for ip in items:
            obj = ip.assigned_object
            parent = getattr(obj, "parent_object", None)
            rows.append([ip.address, get(ip, "status"), get(ip, "role"), ip.dns_name, f"{parent} – {obj}" if parent else obj, ip.description])
        blocks.append(T(["Adresse", "Status", "Rolle", "DNS-Name", "Zugewiesen an", "Beschreibung"], rows))
    return blocks


@section("wireless", "WLANs", "Netzwerk", default=False, hint="SSIDs, Authentifizierung")
def wireless(scope, opts):
    qs = scope.wireless_lans().select_related("group", "vlan").order_by("ssid")
    blocks = [H(1, "WLANs")]
    if not qs.exists():
        return _empty(opts, blocks)
    headers = ["SSID", "Gruppe", "VLAN", "Status", "Authentifizierung", "Verschlüsselung"]
    show_psk = opts.get("include_secrets")
    if show_psk:
        headers.append("PSK")
    rows = []
    for w in qs:
        row = [w.ssid, w.group, w.vlan, get(w, "status"), get(w, "auth_type"), get(w, "auth_cipher")]
        if show_psk:
            row.append(w.auth_psk)
        rows.append(row)
    blocks.append(T(headers, rows))
    return blocks


@section("circuits", "Leitungen", "Netzwerk", default=False, hint="Provider, Leitungs-ID, Bandbreite")
def circuits(scope, opts):
    qs = scope.circuits().select_related("provider", "type", "tenant").order_by("provider__name", "cid")
    blocks = [H(1, "Leitungen")]
    if not qs.exists():
        return _empty(opts, blocks)
    blocks.append(
        T(
            ["Leitungs-ID", "Provider", "Typ", "Status", "Bandbreite (Kbit/s)", "Beschreibung"],
            [[c.cid, c.provider, c.type, get(c, "status"), c.commit_rate, c.description] for c in qs],
        )
    )
    return blocks


# --- Lizenzen (über Plugin-Modelle) ---------------------------------------

DEFAULT_LICENSE_SOURCES = [
    {
        "model": "netbox_lifecycle.licenseassignment",
        "device_field": "device",
        "columns": [
            ("Lizenz", "license"),
            ("Hersteller", "license.manufacturer"),
            ("Gerät", "device"),
            ("Anzahl", "quantity"),
            ("Vertrag", "license.contract"),
            ("Beschreibung", "description"),
        ],
    },
]


@section("licenses", "Lizenzen", "Verträge & Lizenzen", hint="Aus Lizenz-Plugin (z.B. netbox-lifecycle)")
def licenses(scope, opts):
    sources = get_plugin_config("netbox_customer_export", "license_sources") or DEFAULT_LICENSE_SOURCES
    blocks = [H(1, "Lizenzen")]
    found_source = False
    for src in sources:
        try:
            model = apps.get_model(src["model"])
        except (LookupError, ValueError):
            continue
        found_source = True
        from django.db.models import Q

        q = Q(**{f"{src['device_field']}__in": scope.devices()})
        if src.get("tenant_field") and scope.tenants is not None:
            q |= Q(**{f"{src['tenant_field']}__in": scope.tenants})
        qs = scope.restrict(model.objects.filter(q).distinct())
        if qs.exists():
            cols = src["columns"]
            blocks.append(T([c[0] for c in cols], [[get(o, c[1]) for c in cols] for o in qs]))
    if not found_source:
        return _empty(opts, blocks, "Kein Lizenz-Plugin installiert (z.B. netbox-lifecycle) – siehe README.")
    return blocks if len(blocks) > 1 else _empty(opts, blocks)


@section("topology", "Netzwerk-Topologie", "Netzwerk", default=False, hint="Diagramm mit Symbolen, wie Packet Tracer")
def topology(scope, opts):
    from .topology import build_graphs, render_png

    title = H(1, "Netzwerk-Topologie")
    graphs = build_graphs(scope, opts)
    if not graphs:
        return _empty(opts, [title], "Keine verkabelten Geräte gefunden.")
    ports = "ports" in (opts.get("topo_details") or [])
    # Je Standort eine Querformat-Seite; die Abschnittsüberschrift steht mit auf der ersten
    return [
        LANDSCAPE(([title] if i == 0 else []) + [H(2, g.title)], render_png(g, show_ports=ports))
        for i, g in enumerate(graphs)
    ]
