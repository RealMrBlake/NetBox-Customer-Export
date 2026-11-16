"""Lizenzen aus dem Plugin NetBox-SLM (netbox_slm.SoftwareLicense)."""
from datetime import date
from itertools import groupby

from django.apps import apps
from django.db.models import Q
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from .blocks import EMPTY, H, T

SOON_DAYS = 90  # „läuft bald ab“, wenn das Ablaufdatum näher liegt


def is_installed():
    return apps.is_installed("netbox_slm")


def _tenant_groups(scope):
    """Mandantengruppen, deren mandantenlose Lizenzen zum Scope gehören."""
    from tenancy.models import TenantGroup

    if scope.kind == "tenantgroup":
        return scope.obj.get_descendants(include_self=True)
    if scope.kind == "tenant" and scope.obj.group_id:
        # Lizenzen der eigenen Gruppe und übergeordneter Gruppen gelten auch für den Mandanten
        return scope.obj.group.get_ancestors(include_self=True)
    return TenantGroup.objects.none()


def licenses_for_scope(scope):
    """SoftwareLicense-Queryset für den Scope: über Installationen (Gerät/VM/Cluster) und Mandant(engruppe)."""
    from virtualization.models import Cluster

    SoftwareLicense = apps.get_model("netbox_slm", "SoftwareLicense")
    devices = scope.devices()
    vms = scope.virtual_machines()
    clusters = Cluster.objects.filter(Q(virtual_machines__in=vms) | Q(devices__in=devices)).distinct()

    q = (
        Q(installation__device__in=devices)
        | Q(installation__virtualmachine__in=vms)
        | Q(installation__cluster__in=clusters)
    )
    if scope.tenants is not None:
        q |= Q(tenant__in=scope.tenants) | Q(tenant__isnull=True, tenant_group__in=_tenant_groups(scope))
    return (
        scope.restrict(SoftwareLicense.objects.filter(q).distinct())
        .select_related(
            "software_product__manufacturer", "version", "tenant", "tenant_group",
            "installation__device", "installation__virtualmachine", "installation__cluster",
        )
        .order_by("software_product__name", "name")
    )


def _validity(lic, today):
    """(Laufzeit-Text, Status-Text)."""
    if lic.lifetime:
        return _("unlimited"), _("active")
    start = date_format(lic.start_date, "SHORT_DATE_FORMAT") if lic.start_date else ""
    end = date_format(lic.expiration_date, "SHORT_DATE_FORMAT") if lic.expiration_date else ""
    if start and end:
        period = f"{start} – {end}"
    elif end:
        period = _("until %(date)s") % {"date": end}
    elif start:
        period = _("from %(date)s") % {"date": start}
    else:
        period = EMPTY
    if lic.renewal_interval and lic.renewal_interval_unit:
        n = lic.renewal_interval
        every = {
            "days": ngettext("daily", "every %(n)d days", n),
            "months": ngettext("monthly", "every %(n)d months", n),
            "years": ngettext("yearly", "every %(n)d years", n),
        }.get(lic.renewal_interval_unit, f"{n} {lic.renewal_interval_unit}")
        period += " " + _("(renewal %(interval)s)") % {"interval": every % {"n": n}}
    if not lic.expiration_date:
        return period, _("active")
    days = (lic.expiration_date - today).days
    if days < 0:
        return period, _("expired")
    if days <= SOON_DAYS:
        return period, ngettext("expires in %(days)d day", "expires in %(days)d days", days) % {"days": days}
    return period, _("active")


def _support(value):
    return {True: _("Yes"), False: _("No")}.get(value, EMPTY)


def _installed_on(lic):
    inst = lic.installation
    if not inst:
        return None
    target = inst.device or inst.virtualmachine or inst.cluster
    kind = _("Device") if inst.device_id else (_("VM") if inst.virtualmachine_id else _("Cluster"))
    return f"{target} ({kind})" if target else None


def slm_blocks(scope, opts):
    """Tabellen je Hersteller; leer, wenn keine Lizenz zum Scope passt."""
    qs = list(licenses_for_scope(scope))
    if not qs:
        return []
    today = date.today()
    show_key = bool(opts.get("include_secrets"))
    headers = [_("License"), _("Product / version"), _("Type"), _("Quantity"), _("Term"), _("Status"), _("Support"), _("Installed on"), _("Tenant")]
    if show_key:
        headers.append(_("License key"))

    blocks = []
    by_manufacturer = sorted(qs, key=lambda lic: (str(lic.software_product.manufacturer or "~"), str(lic.software_product), lic.name))
    for manufacturer, items in groupby(by_manufacturer, key=lambda lic: lic.software_product.manufacturer):
        rows = []
        for lic in items:
            period, status = _validity(lic, today)
            product = str(lic.software_product) + (f" {lic.version}" if lic.version else "")
            row = [
                lic.name + (f"\n{lic.description}" if lic.description else ""),
                product,
                lic.type or lic.spdx_expression,
                lic.license_amount,
                period,
                status,
                _support(lic.support),
                _installed_on(lic),
                lic.tenant or lic.tenant_group,
            ]
            if show_key:
                row.append(lic.license_key)
            rows.append(row)
        blocks.append(H(2, str(manufacturer) if manufacturer else _("No manufacturer")))
        blocks.append(T(headers, rows))
    return blocks
