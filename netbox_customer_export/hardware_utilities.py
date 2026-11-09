"""CPU & RAM aus dem Plugin Netbox-Utilities (netbox_utilities.DeviceHardware)."""
from django.apps import apps
from django.utils.translation import gettext as _


def is_installed():
    if not apps.is_installed("netbox_utilities"):
        return False
    try:
        apps.get_model("netbox_utilities", "DeviceHardware")
    except LookupError:  # ältere Version ohne CPU & RAM
        return False
    return True


def hardware(device):
    """DeviceHardware des Geräts oder None (nicht installiert / nicht gepflegt)."""
    if not is_installed():
        return None
    return getattr(device, "netbox_utilities_hardware", None)  # RelatedObjectDoesNotExist ist ein AttributeError


def cores_threads(hw):
    """(Kerne, Threads) gesamt oder (None, None)."""
    if not hw or not hw.cpu_id:
        return None, None
    return hw.total_cores, hw.total_threads


def format_memory(gigabytes):
    from netbox_utilities import hardware as helpers

    return helpers.format_memory(gigabytes)


def cpu_text(device):
    """„2 × Intel Xeon Gold 6130“ + Zeile „32 Kerne / 64 Threads“."""
    hw = hardware(device)
    if not hw or not hw.cpu_id:
        return None
    cores, threads = cores_threads(hw)
    return f"{hw.cpu_display}\n" + _("%(cores)s cores / %(threads)s threads") % {"cores": cores, "threads": threads}


def ram_text(device):
    """„384 GB“ + Zeile „12 × 32 GB · DDR4-2666“."""
    hw = hardware(device)
    if not hw or not hw.memory_gb:
        return None
    detail = hw.memory_detail
    return f"{format_memory(hw.memory_gb)}\n{detail}" if detail else format_memory(hw.memory_gb)
