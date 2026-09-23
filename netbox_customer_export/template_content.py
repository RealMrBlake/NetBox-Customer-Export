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


template_extensions = [CustomerExportButton]
