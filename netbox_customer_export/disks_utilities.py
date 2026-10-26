"""Datenträger und RAID-Gruppen aus dem Plugin Netbox-Utilities (netbox_utilities.Disk)."""
from django.apps import apps
from django.utils.formats import date_format
from django.utils.translation import gettext as _

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
    return date_format(value, "SHORT_DATE_FORMAT") if value else None


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
    headers = [_("Slot"), _("Status"), _("Type"), _("Manufacturer / model"), _("Size"), _("Serial number"), _("Firmware"), "RAID"]
    headers += [_("Installed")] * show_installed + [_("Warranty until"), _("Notes")]
    blocks = []
    for device, items in by_device.items():
        slots = sum(b.slot_count for b in DiskBayLayout.objects.filter(device=device))
        summary = helpers.disk_summary(items, slots)
        blocks.append(H(2, device.name or str(device)))
        blocks.append(KV([
            (_("Slots used"), f"{summary['used']} / {slots}" if slots else summary["used"]),
            (_("Raw capacity"), fmt(summary["raw_capacity_gb"])),
            (_("Hot spares"), summary["spares"]),
            (_("Failed"), summary["failed"]),
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
            blocks.append(T([_("RAID group"), _("Level"), _("Disks"), _("Usable"), _("Fault tolerance"), _("Description")], rows))

        rows = []
        for d in items:
            hints = "\n".join(text for _lvl, text in helpers.disk_warnings(d, **warn_cfg))
            row = [
                _slot(d),
                d.get_status_display(),
                " / ".join(x for x in (d.get_disk_type_display(), d.get_interface_display()) if x),
                " ".join(x for x in (d.manufacturer, d.model) if x),
                fmt(d.capacity_gb) if d.capacity_gb else None,
                d.serial,
                d.firmware,
                d.raid_group,
            ]
            if show_installed:
                row.append(_date(getattr(d, "install_date", None)))
            rows.append(row + [_date(d.warranty_end), hints])
        blocks.append(T(headers, rows))
    return blocks
