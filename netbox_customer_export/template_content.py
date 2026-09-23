from django.urls import reverse
from django.utils.html import format_html
from netbox.plugins import PluginTemplateExtension


class CustomerExportButton(PluginTemplateExtension):
    models = ["dcim.site", "dcim.location", "tenancy.tenant", "tenancy.tenantgroup"]

    def buttons(self):
        obj = self.context["object"]
        url = reverse(
            "plugins:netbox_customer_export:export",
            kwargs={"kind": obj._meta.model_name, "pk": obj.pk},
        )
        return format_html(
            '<a href="{}" class="btn btn-primary"><i class="mdi mdi-file-document-outline"></i> Kundendoku</a>',
            url,
        )


class TopologySymbolButton(PluginTemplateExtension):
    """Auf Gerätetyp- und Geräterollen-Seiten: Topologie-Symbol festlegen."""

    models = ["dcim.devicetype", "dcim.devicerole"]

    def buttons(self):
        from .models import TopologySymbol

        user = self.context["request"].user
        if not user.has_perm("netbox_customer_export.add_topologysymbol"):
            return ""
        obj = self.context["object"]
        field = "device_type" if obj._meta.model_name == "devicetype" else "role"
        existing = TopologySymbol.objects.filter(**{field: obj}).first()
        if existing:
            url = existing.get_absolute_url()
        else:
            url = f"{reverse('plugins:netbox_customer_export:symbol_add')}?{field}={obj.pk}"
        return format_html(
            '<a href="{}" class="btn btn-outline-primary"><i class="mdi mdi-shape-outline"></i> Topologie-Symbol</a>', url
        )


template_extensions = [CustomerExportButton, TopologySymbolButton]
