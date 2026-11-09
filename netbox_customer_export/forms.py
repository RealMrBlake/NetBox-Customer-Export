from django import forms
from django.utils.translation import gettext_lazy as _
from dcim.models import DeviceRole, DeviceType, Location, Site
from netbox.plugins import get_plugin_config
from tenancy.models import Tenant, TenantGroup
from utilities.forms.fields import DynamicModelChoiceField

from .branding import get_brandings
from .models import BrandingProfile, TopologySymbol
from .sections import DEFAULT_DEVICE_COLUMNS, DEVICE_COLUMNS, SECTIONS
from .symbols import KIND_CHOICES

FORMAT_CHOICES = (("pdf", "PDF"), ("docx", "Word"), ("html", _("HTML preview")))


class ScopeSelectForm(forms.Form):
    site = DynamicModelChoiceField(queryset=Site.objects.all(), required=False, label=_("Site"))
    location = DynamicModelChoiceField(queryset=Location.objects.all(), required=False, label=_("Location"))
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False, label=_("Tenant"))
    tenantgroup = DynamicModelChoiceField(queryset=TenantGroup.objects.all(), required=False, label=_("Tenant group"))

    def clean(self):
        data = super().clean()
        chosen = [(k, v) for k, v in data.items() if v]
        if len(chosen) != 1:
            raise forms.ValidationError(_("Select exactly one scope."))
        data["kind"], data["obj"] = chosen[0]
        return data


class ExportForm(forms.Form):
    format = forms.ChoiceField(choices=FORMAT_CHOICES, initial="pdf", label=_("Format"))
    title = forms.CharField(max_length=200, label=_("Title"))
    subtitle = forms.CharField(max_length=200, required=False, label=_("Subtitle"))
    author = forms.CharField(max_length=100, required=False, label=_("Created by"))
    branding = forms.ChoiceField(choices=(), label=_("Design / company"))

    sections = forms.MultipleChoiceField(
        choices=[(s.key, s.label) for s in SECTIONS.values()],
        initial=[s.key for s in SECTIONS.values() if s.default],
        widget=forms.CheckboxSelectMultiple,
        label=_("Contents"),
    )

    roles = forms.ModelMultipleChoiceField(
        queryset=DeviceRole.objects.none(), required=False, widget=forms.CheckboxSelectMultiple, label=_("Device roles")
    )
    device_columns = forms.MultipleChoiceField(
        choices=[(k, v[0]) for k, v in DEVICE_COLUMNS.items()],
        initial=DEFAULT_DEVICE_COLUMNS,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_("Device columns"),
    )
    group_by_site = forms.BooleanField(required=False, initial=True, label=_("Group devices by site"))

    disk_install_date = forms.BooleanField(required=False, initial=False, label=_("Show disk installation date"))

    rack_svg = forms.BooleanField(required=False, initial=True, label=_("Embed rack elevations (SVG)"))
    rack_images = forms.BooleanField(required=False, initial=False, label=_("Show device images (as in NetBox)"))
    rack_faces = forms.MultipleChoiceField(
        choices=(("front", _("Front")), ("rear", _("Rear"))),
        initial=["front"],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_("Rack faces"),
    )
    rack_devices = forms.BooleanField(required=False, initial=True, label=_("Device list per rack"))
    rack_pagebreak = forms.BooleanField(required=False, initial=True, label=_("Page break after each rack"))
    rack_photos = forms.MultipleChoiceField(choices=(), required=False, widget=forms.CheckboxSelectMultiple, label=_("Rack photos"))

    topo_details = forms.MultipleChoiceField(
        choices=(("model", _("Model")), ("primary_ip", _("Management IP")), ("ports", _("Ports on links"))),
        initial=["primary_ip"],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_("Labels"),
    )
    topo_scope = forms.MultipleChoiceField(
        choices=(
            ("site", _("Whole network (per site)")),
            ("locations", _("Location overview (connections between locations)")),
            ("rack", _("Per rack")),
        ),
        initial=["site"],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_("Scope"),
    )
    topo_external = forms.BooleanField(
        required=False, initial=True, label=_("Show provider circuits and devices outside the scope")
    )
    topo_isolated = forms.BooleanField(required=False, initial=False, label=_("Show uncabled devices"))

    ip_versions = forms.MultipleChoiceField(
        choices=(("4", "IPv4"), ("6", "IPv6")),
        initial=["4", "6"],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_("IP versions"),
    )

    include_empty = forms.BooleanField(required=False, label=_("List empty sections anyway"))
    include_secrets = forms.BooleanField(required=False, label=_("Include secrets (e.g. Wi-Fi PSK)"))

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
        self.photo_groups = []
        if scope is not None:
            from .rack_photos import grouped

            self.photo_groups = grouped(scope)
            self.fields["rack_photos"].choices = [(str(a.pk), a.name) for _r, atts in self.photo_groups for a in atts]
        if scope is not None:
            role_ids = scope.devices().values("role")
            roles = DeviceRole.objects.filter(pk__in=role_ids).order_by("name")
            self.fields["roles"].queryset = roles
            self.fields["roles"].initial = [r.pk for r in roles]
            self.fields["title"].initial = _("Network documentation %(name)s") % {"name": scope.obj}
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
            "is_default": _("Preselected in the export form."),
            "logo": _("PNG or JPG, shown on the cover page."),
            "docx_template": _(".docx or .dotx: styles, header/footer and margins are applied."),
            "docx_table_style": _("Name as shown in Word, e.g. Grid Table 4 – Accent 1. Empty = own colouring."),
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
    device_type = DynamicModelChoiceField(queryset=DeviceType.objects.all(), required=False, label=_("Device type"))
    role = DynamicModelChoiceField(queryset=DeviceRole.objects.all(), required=False, label=_("Device role"))
    kind = forms.ChoiceField(
        choices=[("", _("Automatic"))] + KIND_CHOICES, required=False, widget=forms.RadioSelect, label=_("Symbol")
    )

    class Meta:
        model = TopologySymbol
        fields = ("device_type", "role", "kind", "icon")
        help_texts = {
            "icon": _("PNG, JPG or GIF, ideally square with a transparent background. Replaces the selected symbol."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["icon"].widget.attrs["class"] = "form-control"
