"""Registry der auswählbaren Dokumentabschnitte."""
from collections import OrderedDict
from dataclasses import dataclass
from itertools import groupby

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext
from netbox.plugins import get_plugin_config

from .blocks import EMPTY, H, IMAGES, KV, LANDSCAPE, P, PAGEBREAK, REF, T, get
from . import hardware_utilities
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

def ip_versions(opts):
    """Gewählte IP-Versionen als Menge {4, 6}. Ohne Formular (z.B. Vorschau) beide."""
    versions = opts.get("ip_versions")
    return {4, 6} if versions is None else {int(v) for v in versions}


def ip_text(ips, opts, sep=", "):
    """IP-Objekte gefiltert nach gewählter Version als Text."""
    versions = ip_versions(opts)
    return sep.join(str(ip.address) for ip in ips if ip and ip.address.version in versions) or None


def primary_ips(obj, opts, sep=", "):
    """Primäre IPv4 und/oder IPv6 eines Geräts oder einer VM, je nach Auswahl."""
    return ip_text([obj.primary_ip4, obj.primary_ip6], opts, sep)


def num(value):
    """Decimal/float ohne überflüssige Nachkommastellen, deutsches Komma: 245, 2,5."""
    if value is None:
        return None
    text = f"{value:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _rack_pos(d, o=None):
    if not d.rack:
        return None
    pos = " / " + _("U %(u)s") % {"u": num(d.position)} if d.position else ""
    return f"{d.rack}{pos}"


DEVICE_COLUMNS = OrderedDict(
    [
        ("name", (gettext_lazy("Name"), lambda d, o: d.name or str(d))),
        ("model", (gettext_lazy("Manufacturer / model"), lambda d, o: f"{d.device_type.manufacturer} {d.device_type.model}")),
        ("site", (gettext_lazy("Site"), lambda d, o: d.site)),
        ("location", (gettext_lazy("Location"), lambda d, o: d.location)),
        ("rack", (gettext_lazy("Rack / U"), _rack_pos)),
        ("status", (gettext_lazy("Status"), lambda d, o: d.get_status_display())),
        ("platform", (gettext_lazy("Platform / OS"), lambda d, o: d.platform)),
        ("primary_ip", (gettext_lazy("Management IP"), lambda d, o: primary_ips(d, o))),
        ("oob_ip", (gettext_lazy("OOB IP"), lambda d, o: ip_text([d.oob_ip], o))),
        ("serial", (gettext_lazy("Serial number"), lambda d, o: d.serial)),
        ("cpu", (gettext_lazy("CPU"), lambda d, o: hardware_utilities.cpu_text(d))),
        ("ram", (gettext_lazy("RAM"), lambda d, o: hardware_utilities.ram_text(d))),
        ("asset_tag", (gettext_lazy("Asset tag"), lambda d, o: d.asset_tag)),
        ("tenant", (gettext_lazy("Tenant"), lambda d, o: d.tenant)),
        ("description", (gettext_lazy("Description"), lambda d, o: d.description)),
    ]
)
DEFAULT_DEVICE_COLUMNS = ["name", "model", "location", "rack", "primary_ip", "serial"]


def _device_table(devices, columns, opts):
    cols = [DEVICE_COLUMNS[c] for c in columns if c in DEVICE_COLUMNS]
    return T([c[0] for c in cols], [[c[1](d, opts) for c in cols] for d in devices])


def _empty(opts, blocks, text=None):
    if opts.get("include_empty"):
        blocks.append(P(text or _("No entries.")))
        return blocks
    return []


# --- Abschnitte -------------------------------------------------------------

@section("overview", gettext_lazy("Overview & site data"), gettext_lazy("General"), hint=gettext_lazy("Key figures, addresses, location tree"))
def overview(scope, opts):
    blocks = [H(1, _("Overview"))]
    counts = [
        (_("Sites"), scope.sites().count()),
        (_("Racks"), scope.racks().count()),
        (_("Devices"), scope.devices().count()),
        (_("Virtual machines"), scope.virtual_machines().count()),
        (_("Prefixes"), scope.prefixes().count()),
        (_("VLANs"), scope.vlans().count()),
        (_("Circuits"), scope.circuits().count()),
    ]
    blocks.append(KV([(f"{scope.label}", scope.obj)] + counts))
    if getattr(scope.obj, "description", ""):
        blocks.append(P(scope.obj.description))

    for site in scope.sites().select_related("region", "group", "tenant"):
        blocks.append(H(2, _("Site %(name)s") % {"name": site.name}))
        blocks.append(
            KV(
                [
                    (_("Status"), site.get_status_display()),
                    (_("Region"), site.region),
                    (_("Tenant"), site.tenant),
                    (_("Facility"), site.facility),
                    (_("Physical address"), site.physical_address),
                    (_("Shipping address"), site.shipping_address),
                    (_("Time zone"), site.time_zone),
                    (_("Description"), site.description),
                ]
            )
        )
        locs = scope.location_objects().filter(site=site)
        if locs.exists():
            blocks.append(
                T(
                    [_("Location"), _("Parent"), _("Status"), _("Description")],
                    [[("  " * loc.level) + loc.name, loc.parent, loc.get_status_display(), loc.description] for loc in locs],
                )
            )
    return blocks


@section("contacts", gettext_lazy("Contacts"), gettext_lazy("General"), hint=gettext_lazy("Contacts of sites, locations, tenants"))
def contacts(scope, opts):
    ContactAssignment = apps.get_model("tenancy", "ContactAssignment")
    targets = [
        (scope.sites(), _("Site")),
        (scope.location_objects(), _("Location")),
        (scope.tenant_objects(), _("Tenant")),
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
    blocks = [H(1, _("Contacts"))]
    if not rows:
        return _empty(opts, blocks)
    blocks.append(T([_("Assigned to"), _("Name"), _("Role"), _("Priority"), _("Phone"), _("Email")], rows))
    return blocks


@section("racks", gettext_lazy("Racks"), gettext_lazy("Infrastructure"), hint=gettext_lazy("By site & location, with rack elevation"))
def racks(scope, opts):
    qs = (
        scope.racks()
        .select_related("site", "location", "role", "tenant", "rack_type")
        .order_by("site__name", "location__name", "name")
    )
    blocks = [H(1, _("Racks"))]
    if not qs.exists():
        return _empty(opts, blocks)
    photos = _rack_photos(scope, opts)
    for site, site_racks in groupby(qs, key=lambda r: r.site):
        blocks.append(H(2, _("Site %(name)s") % {"name": site}))
        for location, loc_racks in groupby(site_racks, key=lambda r: r.location):
            blocks.append(H(3, _("Location %(name)s") % {"name": location} if location else _("No location")))
            for rack in loc_racks:
                rack_heading = H(4, _("Rack %(name)s") % {"name": rack.name})
                blocks.append(rack_heading)
                blocks.append(
                    KV(
                        [
                            (_("Status"), rack.get_status_display()),
                            (_("Role"), rack.role),
                            (_("Type"), rack.rack_type),
                            (_("Height"), _("%(u)s U") % {"u": rack.u_height}),
                            (_("Facility ID"), rack.facility_id),
                            (_("Tenant"), rack.tenant),
                            (_("Description"), rack.description),
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
                        caption = _("Front") if face == "front" else _("Rear")
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
                            errors.append(_("Rack elevation (%(face)s) could not be created: %(error)s") % {"face": caption, "error": svg_error})
                    if images:
                        blocks.append(IMAGES(images))
                    blocks += [P(e) for e in errors]
                if opts.get("rack_devices"):
                    devs = scope.restrict(rack.devices.all()).select_related("device_type__manufacturer").order_by("-position", "name")
                    if devs.exists():
                        blocks.append(
                            T(
                                [_("U"), _("Device"), _("Manufacturer / model"), _("Face")],
                                [
                                    [num(d.position) if d.position else EMPTY, d.name, f"{d.device_type.manufacturer} {d.device_type.model}", d.get_face_display() if d.face else EMPTY]
                                    for d in devs
                                ],
                            )
                        )
                if rack.pk in photos:
                    blocks += _photo_appendix(opts, rack, rack_heading, photos[rack.pk])
                if opts.get("rack_pagebreak"):
                    blocks.append(PAGEBREAK())
    return blocks


def _rack_photos(scope, opts):
    """Ausgewählte Bildanhänge je Rack-ID."""
    selected = set(opts.get("rack_photos") or [])
    if not selected:
        return {}
    from . import rack_photos

    out = {}
    for rack, att in rack_photos.attachments(scope):
        if str(att.pk) in selected:
            out.setdefault(rack.pk, []).append(att)
    return out


def _photo_appendix(opts, rack, rack_heading, atts):
    """Legt die Fotos im Anhang ab (opts["_appendix"]) und liefert den Verweis unter der Rack-Ansicht."""
    from . import rack_photos

    images = [(None, rack_photos.caption(a), data) for a in atts if (data := rack_photos.load_jpeg(a))]
    if not images:
        return []
    appendix = opts.setdefault("_appendix", [])
    if not appendix:
        appendix.append(H(1, _("Appendix: rack photos")))
    where = " / ".join(str(x) for x in (rack.site, rack.location) if x)
    heading = H(2, _("Rack %(name)s") % {"name": rack.name} + (f" ({where})" if where else ""))
    appendix.append(heading)
    for i in range(0, len(images), 2):  # zwei Fotos je Zeile
        appendix.append(IMAGES(images[i:i + 2], photos=True))
    appendix.append(REF(_("Back to rack elevation"), rack_heading.anchor, prefix="↑ "))
    n = len(images)
    return [REF(
        _("Appendix rack photos – rack %(name)s") % {"name": rack.name},
        heading.anchor,
        prefix=ngettext("%(n)d photo, see ", "%(n)d photos, see ", n) % {"n": n},
    )]


@section("devices", gettext_lazy("Devices"), gettext_lazy("Infrastructure"), hint=gettext_lazy("Tables per device role"))
def devices(scope, opts):
    blocks = [H(1, _("Devices"))]
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
                blocks.append(H(3, _("Site %(name)s") % {"name": site}))
                blocks.append(_device_table(list(site_devs), columns, opts))
        else:
            blocks.append(_device_table(devs, columns, opts))
    return blocks if found else _empty(opts, blocks)


@section("disks", gettext_lazy("Disks & RAID"), gettext_lazy("Infrastructure"), default=False, hint=gettext_lazy("From Netbox-Utilities (if installed)"))
def disks(scope, opts):
    from . import disks_utilities

    blocks = [H(1, _("Disks & RAID"))]
    if not disks_utilities.is_installed():
        return _empty(opts, blocks, _("No disks recorded."))
    blocks += disks_utilities.disk_blocks(scope, opts)
    return blocks if len(blocks) > 1 else _empty(opts, blocks)


@section("floorplans", gettext_lazy("Floor plans"), gettext_lazy("Infrastructure"), default=False, hint=gettext_lazy("From NetBox-FloorPlan (if installed)"))
def floorplans(scope, opts):
    from . import floorplan

    blocks = [H(1, _("Floor plans"))]
    if not floorplan.is_installed():
        return _empty(opts, blocks, _("No floor plans recorded."))
    blocks += floorplan.floorplan_blocks(scope, opts)
    return blocks if len(blocks) > 1 else _empty(opts, blocks, _("No floor plans recorded."))


@section("power", gettext_lazy("Power"), gettext_lazy("Infrastructure"), default=False, hint=gettext_lazy("Power panels & feeds"))
def power(scope, opts):
    qs = scope.power_feeds().select_related("power_panel", "rack").order_by("power_panel__name", "name")
    blocks = [H(1, _("Power"))]
    if not qs.exists():
        return _empty(opts, blocks)
    blocks.append(
        T(
            [_("Panel"), _("Feed"), _("Rack"), _("Status"), _("Type"), _("Phase"), _("Voltage"), _("Amperage")],
            [[f.power_panel, f.name, f.rack, get(f, "status"), get(f, "type"), get(f, "phase"), f"{f.voltage} V", f"{f.amperage} A"] for f in qs],
        )
    )
    return blocks


def _mb(value):
    """MB als lesbare Größe (VM-RAM/-Disk sind in NetBox in MB gespeichert)."""
    if not value:
        return EMPTY
    for unit, size in (("TB", 1024 ** 2), ("GB", 1024)):
        if value >= size:
            return f"{value / size:.1f} {unit}".replace(".0 ", " ").replace(".", ",")
    return f"{value} MB"


def _host_resources(hosts):
    """Summe der physischen Kerne, Threads und RAM (GB) aller Hosts mit gepflegter Hardware."""
    cores = threads = ram = 0
    for host in hosts:
        hw = hardware_utilities.hardware(host)
        c, t = hardware_utilities.cores_threads(hw)
        cores, threads = cores + (c or 0), threads + (t or 0)
        ram += (hw.memory_gb or 0) if hw else 0
    return cores, threads, ram


def _vm_totals(vms):
    return (
        sum(vm.vcpus or 0 for vm in vms),
        sum(vm.memory or 0 for vm in vms),
        sum(vm.disk or 0 for vm in vms),
    )


@section("clusters", gettext_lazy("Virtualization clusters"), gettext_lazy("Infrastructure"), default=False, hint=gettext_lazy("Hosts and resources per cluster"))
def clusters(scope, opts):
    qs = scope.clusters().select_related("type", "group", "tenant").order_by("group__name", "name")
    blocks = [H(1, _("Virtualization clusters"))]
    if not qs.exists():
        return _empty(opts, blocks)
    vms_by_cluster = {}
    for vm in scope.virtual_machines().select_related("device"):
        vms_by_cluster.setdefault(vm.cluster_id, []).append(vm)

    summary, details = [], []
    for cluster in qs:
        vms = vms_by_cluster.get(cluster.pk, [])
        hosts = list(scope.restrict(cluster.devices.all()).select_related("device_type__manufacturer").order_by("name"))
        vcpu, ram, disk = _vm_totals(vms)
        active = sum(1 for vm in vms if vm.status == "active")
        p_cores, p_threads, p_ram = _host_resources(hosts)
        ram_pct = f" ({round(ram / (p_ram * 1024) * 100)} %)" if ram and p_ram else ""
        summary.append([
            cluster.name, cluster.type, len(hosts), f"{active} / {len(vms)}",
            f"{num(vcpu)} / {p_cores}" if vcpu and p_cores else num(vcpu) if vcpu else EMPTY,
            f"{_mb(ram)} / {hardware_utilities.format_memory(p_ram)}" if ram and p_ram else _mb(ram),
            _mb(disk),
        ])

        details.append(H(2, _("Cluster %(name)s") % {"name": cluster.name}))
        details.append(KV([
            (_("Type"), cluster.type),
            (_("Group"), cluster.group),
            (_("Status"), get(cluster, "status")),
            (_("Scope"), getattr(cluster, "scope", None)),
            (_("Tenant"), cluster.tenant),
            (_("Hosts"), len(hosts)),
            (_("VMs active / total"), f"{active} / {len(vms)}"),
            (_("Cores / threads (hosts)"), f"{p_cores} / {p_threads}" if p_cores else None),
            (_("RAM (hosts)"), hardware_utilities.format_memory(p_ram) if p_ram else None),
            (_("vCPU (total of VMs)"), num(vcpu) if vcpu else None),
            (_("vCPU per core"), f"{num(round(float(vcpu) / p_cores, 1))} : 1" if vcpu and p_cores else None),
            (_("RAM (total of VMs)"), (_mb(ram) + ram_pct) if ram else None),
            (_("Storage (total)"), _mb(disk) if disk else None),
            (_("Description"), cluster.description),
        ]))
        if hosts:
            rows = []
            for host in hosts:
                host_vms = [vm for vm in vms if vm.device_id == host.pk]
                h_vcpu, h_ram, _h_disk = _vm_totals(host_vms)
                h_cores, _t, h_pram = _host_resources([host])
                rows.append([
                    host.name,
                    f"{host.device_type.manufacturer} {host.device_type.model}",
                    hardware_utilities.cpu_text(host),
                    hardware_utilities.format_memory(h_pram) if h_pram else None,
                    len(host_vms) if host_vms else EMPTY,
                    (f"{num(h_vcpu)} ({num(round(float(h_vcpu) / h_cores, 1))} : 1)" if h_cores else num(h_vcpu)) if h_vcpu else EMPTY,
                    (_mb(h_ram) + (f" ({round(h_ram / (h_pram * 1024) * 100)} %)" if h_pram else "")) if h_ram else EMPTY,
                ])
            details.append(T([_("Host"), _("Manufacturer / model"), _("CPU"), _("RAM"), _("VMs"), _("vCPU"), _("RAM of VMs")], rows))
            if any(vm.device_id is None for vm in vms):
                details.append(P(_("VMs without a fixed host are only included in the cluster totals.")))

    blocks.append(T([_("Cluster"), _("Type"), _("Hosts"), _("VMs active / total"), _("vCPU / cores"), _("RAM of VMs / hosts"), _("Storage")], summary))
    return blocks + details


@section("vms", gettext_lazy("Virtual machines"), gettext_lazy("Infrastructure"), default=False, hint=gettext_lazy("Cluster, resources, IP"))
def vms(scope, opts):
    qs = scope.virtual_machines().select_related("cluster", "role", "platform", "primary_ip4", "primary_ip6").order_by("cluster__name", "name")
    blocks = [H(1, _("Virtual machines"))]
    if not qs.exists():
        return _empty(opts, blocks)
    blocks.append(
        T(
            [_("Name"), _("Cluster"), _("Role"), _("Status"), _("OS"), "vCPU", _("RAM (MB)"), _("Disk (MB)"), "IP"],
            [[vm.name, vm.cluster, vm.role, get(vm, "status"), vm.platform, vm.vcpus, vm.memory, vm.disk, primary_ips(vm, opts)] for vm in qs],
        )
    )
    return blocks


@section("vrfs", gettext_lazy("VRFs"), gettext_lazy("Network"), hint=gettext_lazy("Including route targets"))
def vrfs(scope, opts):
    qs = scope.vrfs().select_related("tenant").prefetch_related("import_targets", "export_targets").order_by("name")
    blocks = [H(1, _("VRFs"))]
    if not qs.exists():
        return _empty(opts, blocks)
    blocks.append(
        T(
            [_("Name"), "RD", _("Tenant"), _("Import RT"), _("Export RT"), _("Description")],
            [[v.name, v.rd, v.tenant, v.import_targets, v.export_targets, v.description] for v in qs],
        )
    )
    return blocks


@section("prefixes", gettext_lazy("IP networks"), gettext_lazy("Network"), hint=gettext_lazy("Prefixes grouped by VRF"))
def prefixes(scope, opts):
    qs = scope.prefixes().select_related("vrf", "vlan", "role", "tenant").order_by("vrf__name", "prefix")
    qs = qs.filter(prefix__family__in=ip_versions(opts))
    blocks = [H(1, _("IP networks"))]
    if not qs.exists():
        return _empty(opts, blocks)
    for vrf, items in groupby(qs, key=lambda p: p.vrf):
        blocks.append(H(2, f"VRF {vrf}" if vrf else _("Global")))
        blocks.append(
            T(
                [_("Prefix"), "VLAN", _("Role"), _("Status"), _("Scope"), _("Description")],
                [[p.prefix, p.vlan, p.role, get(p, "status"), p.scope, p.description] for p in items],
            )
        )
    return blocks


@section("vlans", gettext_lazy("VLANs"), gettext_lazy("Network"), hint=gettext_lazy("VID, name, group, role"))
def vlans(scope, opts):
    qs = scope.vlans().select_related("group", "site", "role", "tenant").order_by("group__name", "vid")
    blocks = [H(1, _("VLANs"))]
    if not qs.exists():
        return _empty(opts, blocks)
    blocks.append(
        T(
            ["VID", _("Name"), _("Group"), _("Site"), _("Role"), _("Status"), _("Description")],
            [[v.vid, v.name, v.group, v.site, v.role, get(v, "status"), v.description] for v in qs],
        )
    )
    return blocks


@section("ips", gettext_lazy("IP addresses"), gettext_lazy("Network"), default=False, hint=gettext_lazy("Detailed – can get long"))
def ips(scope, opts):
    qs = scope.ip_addresses().select_related("vrf", "tenant").prefetch_related("assigned_object").order_by("vrf__name", "address")
    qs = qs.filter(address__family__in=ip_versions(opts))
    blocks = [H(1, _("IP addresses"))]
    if not qs.exists():
        return _empty(opts, blocks)
    for vrf, items in groupby(qs, key=lambda i: i.vrf):
        blocks.append(H(2, f"VRF {vrf}" if vrf else _("Global")))
        rows = []
        for ip in items:
            obj = ip.assigned_object
            parent = getattr(obj, "parent_object", None)
            rows.append([ip.address, get(ip, "status"), get(ip, "role"), ip.dns_name, f"{parent} – {obj}" if parent else obj, ip.description])
        blocks.append(T([_("Address"), _("Status"), _("Role"), _("DNS name"), _("Assigned to"), _("Description")], rows))
    return blocks


@section("wireless", gettext_lazy("Wireless LANs"), gettext_lazy("Network"), default=False, hint=gettext_lazy("SSIDs, authentication"))
def wireless(scope, opts):
    qs = scope.wireless_lans().select_related("group", "vlan").order_by("ssid")
    blocks = [H(1, _("Wireless LANs"))]
    if not qs.exists():
        return _empty(opts, blocks)
    headers = ["SSID", _("Group"), "VLAN", _("Status"), _("Authentication"), _("Cipher")]
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


@section("circuits", gettext_lazy("Circuits"), gettext_lazy("Network"), default=False, hint=gettext_lazy("Provider, circuit ID, bandwidth"))
def circuits(scope, opts):
    qs = scope.circuits().select_related("provider", "type", "tenant").order_by("provider__name", "cid")
    blocks = [H(1, _("Circuits"))]
    if not qs.exists():
        return _empty(opts, blocks)
    blocks.append(
        T(
            [_("Circuit ID"), _("Provider"), _("Type"), _("Status"), _("Commit rate (Kbps)"), _("Description")],
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
            (gettext_lazy("License"), "license"),
            (gettext_lazy("Manufacturer"), "license.manufacturer"),
            (gettext_lazy("Device"), "device"),
            (gettext_lazy("Quantity"), "quantity"),
            (gettext_lazy("Contract"), "license.contract"),
            (gettext_lazy("Description"), "description"),
        ],
    },
]


@section("licenses", gettext_lazy("Licenses"), gettext_lazy("Contracts & licenses"), hint=gettext_lazy("From NetBox-SLM or another license plugin"))
def licenses(scope, opts):
    from . import licenses_slm

    sources = get_plugin_config("netbox_customer_export", "license_sources") or DEFAULT_LICENSE_SOURCES
    blocks = [H(1, _("Licenses"))]
    found_source = False
    if licenses_slm.is_installed():
        found_source = True
        blocks += licenses_slm.slm_blocks(scope, opts)
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
        return _empty(opts, blocks, _("No license plugin installed (NetBox-SLM or netbox-lifecycle) – see README."))
    return blocks if len(blocks) > 1 else _empty(opts, blocks)


@section("topology", gettext_lazy("Network topology"), gettext_lazy("Network"), default=False, hint=gettext_lazy("Diagram with symbols, like Packet Tracer"))
def topology(scope, opts):
    from .topology import build_graphs, build_location_graphs, render_png

    title = H(1, _("Network topology"))
    scopes = opts.get("topo_scope") or ["site"]
    ports = "ports" in (opts.get("topo_details") or [])
    pages = []  # (Überschriften, Graph) – je eine Querformat-Seite
    if "site" in scopes:
        pages += [([H(2, g.title)], g) for g in build_graphs(scope, opts, per="site")]
    if "locations" in scopes:
        locs = build_location_graphs(scope, opts)
        pages += [(([H(2, _("Location overview"))] if i == 0 else []) + [H(3, g.title)], g) for i, g in enumerate(locs)]
    if "rack" in scopes:
        racks = build_graphs(scope, opts, per="rack")
        # Rack-Seiten unter einer gemeinsamen Zwischenüberschrift, Racks selbst eine Ebene tiefer (kürzeres Inhaltsverzeichnis)
        pages += [(([H(2, _("Topology per rack"))] if i == 0 else []) + [H(3, g.title)], g) for i, g in enumerate(racks)]
    if not pages:
        return _empty(opts, [title], _("No cabled devices found."))
    # Die Abschnittsüberschrift steht mit auf der ersten Seite
    return [
        LANDSCAPE(([title] if i == 0 else []) + headings, render_png(g, show_ports=ports))
        for i, (headings, g) in enumerate(pages)
    ]
