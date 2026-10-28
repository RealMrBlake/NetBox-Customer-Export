"""Datenträger und RAID-Gruppen aus dem Plugin Netbox-Utilities (netbox_utilities.Disk)."""
from django.apps import apps

from .blocks import EMPTY, H, KV, T

ACTIVE_STATUSES = ("active", "spare", "failed", "planned")  # ohne „ausgebaut/ersetzt“


def is_installed():
    if not apps.is_installed("netbox_utilities"):
        return False
    try:
        apps.get_model("netbox_utilities", "Disk")
    except LookupError:  # ältere Version ohne Datenträger
        return False
    return True


def _helpers():
    from netbox_utilities import disks

    return disks


def _date(value):
    return value.strftime("%d.%m.%Y") if value else None


def _slot(disk):
    bay = disk.bay.name if disk.bay_id and disk.device.netbox_utilities_disk_bays.count() > 1 else ""
    return f"{bay} {disk.slot}".strip()


def disk_blocks(scope, opts):
    """Je Gerät: Kennzahlen, RAID-Gruppen und Datenträger. Leer, wenn keine Datenträger im Scope."""
    Disk = apps.get_model("netbox_utilities", "Disk")
    RAIDGroup = apps.get_model("netbox_utilities", "RAIDGroup")
    DiskBayLayout = apps.get_model("netbox_utilities", "DiskBayLayout")
    helpers = _helpers()
    fmt = helpers.format_capacity
    warn_cfg = helpers.warning_settings()

    disks = list(
        scope.restrict(Disk.objects.filter(device__in=scope.devices(), status__in=ACTIVE_STATUSES))
        .select_related("device", "bay", "raid_group")
        .order_by("device__name", "bay__weight", "bay__name", "slot")
    )
    if not disks:
        return []

    by_device = {}
    for disk in disks:
        by_device.setdefault(disk.device, []).append(disk)

    show_installed = bool(opts.get("disk_install_date"))
    headers = ["Steckplatz", "Status", "Datenträger", "Größe", "Seriennummer", "RAID"]
    headers += ["Eingebaut"] * show_installed + ["Garantie bis", "Hinweise"]
    blocks = []
    for device, items in by_device.items():
        slots = sum(b.slot_count for b in DiskBayLayout.objects.filter(device=device))
        summary = helpers.disk_summary(items, slots)
        blocks.append(H(2, device.name or str(device)))
        blocks.append(KV([
            ("Steckplätze belegt", f"{summary['used']} / {slots}" if slots else summary["used"]),
            ("Rohkapazität", fmt(summary["raw_capacity_gb"])),
            ("Hot Spares", summary["spares"]),
            ("Defekt", summary["failed"]),
        ]))

        groups = list(RAIDGroup.objects.filter(device=device).order_by("name"))
        if groups:
            rows = []
            for group in groups:
                members = [d for d in items if d.raid_group_id == group.pk and d.status in ("active", "failed")]
                usable, tolerated, _err = helpers.raid_usable_capacity(group.level, [d.capacity_gb for d in members], group.spans)
                rows.append([
                    group.name,
                    group.get_level_display(),
                    len(members),
                    fmt(usable) if usable else EMPTY,
                    tolerated if tolerated is not None else EMPTY,
                    group.description,
                ])
            blocks.append(T(["RAID-Gruppe", "Level", "Datenträger", "Nutzbar", "Ausfalltoleranz", "Beschreibung"], rows))

        rows = []
        for d in items:
            hints = "\n".join(text for _lvl, text in helpers.disk_warnings(d, **warn_cfg))
            row = [
                _slot(d),
                d.get_status_display(),
                "\n".join(x for x in (
                    " ".join(x for x in (d.manufacturer, d.model) if x),
                    " / ".join(x for x in (d.get_disk_type_display(), d.get_interface_display()) if x),
                ) if x),
                fmt(d.capacity_gb) if d.capacity_gb else None,
                "\n".join(x for x in (d.serial, f"FW {d.firmware}" if d.firmware else "") if x),
                d.raid_group.name if d.raid_group_id else None,
            ]
            if show_installed:
                row.append(_date(getattr(d, "install_date", None)))
            rows.append(row + [_date(d.warranty_end), hints])
        blocks.append(T(headers, rows))
    return blocks
