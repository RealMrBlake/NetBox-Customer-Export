from django import forms
from dcim.models import DeviceRole, Location, Site
from netbox.plugins import get_plugin_config
from tenancy.models import Tenant, TenantGroup
from utilities.forms.fields import DynamicModelChoiceField

from .branding import get_brandings
from .sections import DEFAULT_DEVICE_COLUMNS, DEVICE_COLUMNS, SECTIONS

FORMAT_CHOICES = (("pdf", "PDF"), ("docx", "Word (.docx)"), ("html", "HTML-Vorschau"))


class ScopeSelectForm(forms.Form):
    site = DynamicModelChoiceField(queryset=Site.objects.all(), required=False, label="Standort")
    location = DynamicModelChoiceField(queryset=Location.objects.all(), required=False, label="Lokation")
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False, label="Mandant")
    tenantgroup = DynamicModelChoiceField(queryset=TenantGroup.objects.all(), required=False, label="Mandantengruppe")

    def clean(self):
        data = super().clean()
        chosen = [(k, v) for k, v in data.items() if v]
        if len(chosen) != 1:
            raise forms.ValidationError("Bitte genau einen Scope auswählen.")
        data["kind"], data["obj"] = chosen[0]
        return data


class ExportForm(forms.Form):
    format = forms.ChoiceField(choices=FORMAT_CHOICES, initial="pdf", label="Format")
    title = forms.CharField(max_length=200, label="Titel")
    subtitle = forms.CharField(max_length=200, required=False, label="Untertitel")
    author = forms.CharField(max_length=100, required=False, label="Erstellt von")
    branding = forms.ChoiceField(choices=(), label="Design / Firma")

    sections = forms.MultipleChoiceField(
        choices=[(s.key, s.label) for s in SECTIONS.values()],
        initial=[s.key for s in SECTIONS.values() if s.default],
        widget=forms.CheckboxSelectMultiple,
        label="Inhalte",
    )

    roles = forms.ModelMultipleChoiceField(
        queryset=DeviceRole.objects.none(), required=False, widget=forms.CheckboxSelectMultiple, label="Geräterollen"
    )
    device_columns = forms.MultipleChoiceField(
        choices=[(k, v[0]) for k, v in DEVICE_COLUMNS.items()],
        initial=DEFAULT_DEVICE_COLUMNS,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Gerätespalten",
    )
    group_by_site = forms.BooleanField(required=False, initial=True, label="Geräte nach Standort gruppieren")

    rack_svg = forms.BooleanField(required=False, initial=True, label="Rack-Ansichten (SVG) einbetten")
    rack_faces = forms.MultipleChoiceField(
        choices=(("front", "Vorderseite"), ("rear", "Rückseite")),
        initial=["front"],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Rack-Seiten",
    )
    rack_devices = forms.BooleanField(required=False, initial=True, label="Geräteliste je Rack")
    rack_pagebreak = forms.BooleanField(required=False, initial=True, label="Seitenumbruch nach jedem Rack")

    include_empty = forms.BooleanField(required=False, label="Leere Abschnitte trotzdem aufführen")
    include_secrets = forms.BooleanField(required=False, label="Geheimnisse (z.B. WLAN-PSK) mit exportieren")

    def __init__(self, *args, scope=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Ohne diese Klasse stellt NetBox' CSS die Checkboxen als leere Eingabefelder dar
        for field in self.fields.values():
            if isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                field.widget.attrs["class"] = "form-check-input"
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select"
            elif isinstance(field.widget, forms.TextInput):
                field.widget.attrs["class"] = "form-control"
        self.fields["branding"].choices = [(k, b["name"]) for k, b in get_brandings().items()]
        if scope is not None:
            role_ids = scope.devices().values("role")
            roles = DeviceRole.objects.filter(pk__in=role_ids).order_by("name")
            self.fields["roles"].queryset = roles
            self.fields["roles"].initial = [r.pk for r in roles]
            self.fields["title"].initial = f"Netzwerkdokumentation {scope.obj}"
            self.fields["subtitle"].initial = f"{scope.label}: {scope.obj}"
        if not get_plugin_config("netbox_customer_export", "allow_secrets"):
            del self.fields["include_secrets"]
