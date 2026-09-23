"""Ermittelt, welche Objekte zu einem Export-Scope (Standort, Lokation, Mandant, Mandantengruppe) gehören."""
from django.db.models import Q

from circuits.models import Circuit
from dcim.models import Device, Location, PowerFeed, Rack, Site
from ipam.models import VLAN, VRF, IPAddress, Prefix
from tenancy.models import Tenant, TenantGroup
from virtualization.models import VirtualMachine
from wireless.models import WirelessLAN

SCOPE_MODELS = {
    "site": Site,
    "location": Location,
    "tenant": Tenant,
    "tenantgroup": TenantGroup,
}

SCOPE_LABELS = {
    "site": "Standort",
    "location": "Lokation",
    "tenant": "Mandant",
    "tenantgroup": "Mandantengruppe",
}

NONE = Q(pk__in=[])


class Scope:
    def __init__(self, kind, obj, user):
        self.kind = kind
        self.obj = obj
        self.user = user
        self.label = SCOPE_LABELS[kind]
        self.locations = None
        self.tenants = None
        if kind == "location":
            self.locations = obj.get_descendants(include_self=True)
        elif kind == "tenant":
            self.tenants = Tenant.objects.filter(pk=obj.pk)
        elif kind == "tenantgroup":
            self.tenants = Tenant.objects.filter(group__in=obj.get_descendants(include_self=True))

    # -- Hilfsfunktionen --------------------------------------------------

    def restrict(self, qs):
        if hasattr(qs, "restrict"):
            return qs.restrict(self.user, "view")
        return qs

    def _q(self, site=(), location=(), tenant=("tenant",)):
        """Baut einen Q-Filter; jedes Argument ist eine Liste von Feldpfaden, die ODER-verknüpft werden."""
        if self.kind == "site":
            paths, value = site, self.obj
        elif self.kind == "location":
            paths, value = [f"{p}__in" for p in location], self.locations
        else:
            paths, value = [f"{p}__in" for p in tenant], self.tenants
        q = NONE
        for p in paths:
            q |= Q(**{p: value})
        return q

    def _qs(self, model, **paths):
        return self.restrict(model.objects.filter(self._q(**paths)).distinct())

    # -- Objekte ----------------------------------------------------------

    def sites(self):
        if self.kind == "site":
            return self.restrict(Site.objects.filter(pk=self.obj.pk))
        if self.kind == "location":
            return self.restrict(Site.objects.filter(pk=self.obj.site_id))
        return self._qs(Site, tenant=("tenant", "devices__tenant", "racks__tenant"))

    def location_objects(self):
        return self._qs(Location, site=("site",), location=("pk",), tenant=("tenant", "devices__tenant"))

    def racks(self):
        return self._qs(Rack, site=("site",), location=("location",), tenant=("tenant", "devices__tenant"))

    def devices(self):
        return self._qs(Device, site=("site",), location=("location",))

    def virtual_machines(self):
        return self._qs(
            VirtualMachine,
            site=("site", "cluster___site"),
            location=("cluster___location", "device__location"),
        )

    def prefixes(self):
        return self._qs(Prefix, site=("_site",), location=("_location",))

    def vlans(self):
        return self._qs(
            VLAN,
            site=("site", "prefixes___site"),
            location=(
                "prefixes___location",
                "interfaces_as_untagged__device__location",
                "interfaces_as_tagged__device__location",
            ),
        )

    def vrfs(self):
        q = Q(prefixes__in=self.prefixes())
        if self.tenants is not None:
            q |= Q(tenant__in=self.tenants)
        return self.restrict(VRF.objects.filter(q).distinct())

    def ip_addresses(self):
        q = Q(interface__device__in=self.devices()) | Q(vminterface__virtual_machine__in=self.virtual_machines())
        if self.tenants is not None:
            q |= Q(tenant__in=self.tenants)
        return self.restrict(IPAddress.objects.filter(q).distinct())

    def circuits(self):
        return self._qs(Circuit, site=("terminations___site",), location=("terminations___location",))

    def wireless_lans(self):
        return self._qs(WirelessLAN, site=("_site",), location=("_location",))

    def power_feeds(self):
        return self._qs(PowerFeed, site=("power_panel__site",), location=("power_panel__location",))

    def tenant_objects(self):
        if self.tenants is not None:
            return self.restrict(self.tenants)
        return self.restrict(Tenant.objects.filter(devices__in=self.devices()).distinct())
