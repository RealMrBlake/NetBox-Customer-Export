from django import forms
from dcim.models import DeviceRole, DeviceType, Location, Site
from netbox.plugins import get_plugin_config
from tenancy.models import Tenant, TenantGroup
from utilities.forms.fields import DynamicModelChoiceField

from .branding import get_brandings
from .models import BrandingProfile, TopologySymbol
from .sections import DEFAULT_DEVICE_COLUMNS, DEVICE_COLUMNS, SECTIONS
from .symbols import KIND_CHOICES

FORMAT_CHOICES = (("pdf", "PDF"), ("docx", "Word"), ("html", "HTML-Vorschau"), ("drawio", "draw.io"))


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
    rack_images = forms.BooleanField(required=False, initial=False, label="Gerätebilder anzeigen (wie in NetBox)")
    rack_faces = forms.MultipleChoiceField(
        choices=(("front", "Vorderseite"), ("rear", "Rückseite")),
        initial=["front"],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Rack-Seiten",
    )
    rack_devices = forms.BooleanField(required=False, initial=True, label="Geräteliste je Rack")
    rack_pagebreak = forms.BooleanField(required=False, initial=True, label="Seitenumbruch nach jedem Rack")

    topo_details = forms.MultipleChoiceField(
        choices=(("model", "Modell"), ("primary_ip", "Management-IP"), ("ports", "Ports an Verbindungen")),
        initial=["primary_ip"],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Beschriftung",
    )
    topo_external = forms.BooleanField(
        required=False, initial=True, label="Provider-Leitungen & Geräte außerhalb anzeigen"
    )
    topo_isolated = forms.BooleanField(required=False, initial=False, label="Unverkabelte Geräte anzeigen")

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


COLOR_FIELDS = ("primary_color", "accent_color", "header_text_color", "label_bg_color", "stripe_color")


class ColorInput(forms.TextInput):
    """<input type="color">: Anzeige mit #, gespeichert wird ohne #."""

    input_type = "color"

    def format_value(self, value):
        return f"#{value.lstrip('#')}" if value else None

    def value_from_datadict(self, data, files, name):
        value = super().value_from_datadict(data, files, name)
        return value.lstrip("#").upper() if value else value


class BrandingProfileForm(forms.ModelForm):
    class Meta:
        model = BrandingProfile
        exclude = ("last_updated",)
        widgets = {
            **{f: ColorInput(attrs={"class": "form-control form-control-color"}) for f in COLOR_FIELDS},
            "extra_css": forms.Textarea(attrs={"rows": 4, "class": "form-control font-monospace"}),
        }
        help_texts = {
            "is_default": "Wird im Exportformular vorausgewählt.",
            "logo": "PNG oder JPG, erscheint auf dem Deckblatt.",
            "docx_template": ".docx oder .dotx: Formatvorlagen, Kopf-/Fußzeile und Ränder werden übernommen.",
            "docx_table_style": "Name wie in Word angezeigt, z.B. Gitternetztabelle 4 – Akzent 1. Leer = eigene Einfärbung.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            w = field.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs.setdefault("class", "form-check-input")
            else:
                w.attrs.setdefault("class", "form-control")


class TopologySymbolForm(forms.ModelForm):
    device_type = DynamicModelChoiceField(queryset=DeviceType.objects.all(), required=False, label="Gerätetyp")
    role = DynamicModelChoiceField(queryset=DeviceRole.objects.all(), required=False, label="Geräterolle")
    kind = forms.ChoiceField(
        choices=[("", "Automatisch")] + KIND_CHOICES, required=False, widget=forms.RadioSelect, label="Symbol"
    )

    class Meta:
        model = TopologySymbol
        fields = ("device_type", "role", "kind", "icon")
        help_texts = {
            "icon": "PNG, JPG oder GIF, am besten quadratisch mit transparentem Hintergrund. Ersetzt das gewählte Symbol.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["icon"].widget.attrs["class"] = "form-control"
