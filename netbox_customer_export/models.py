from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

hex_color = RegexValidator(r"^[0-9A-Fa-f]{6}$", _("Expected a hex colour without #, e.g. 1F4E79"))


def _color(default, verbose_name):
    return models.CharField(max_length=6, default=default, validators=[hex_color], verbose_name=verbose_name)


class BrandingProfile(models.Model):
    """In NetBox gepflegtes Design-Profil (Alternative/Ergänzung zu PLUGINS_CONFIG['brandings'])."""

    name = models.CharField(max_length=100, unique=True, verbose_name=_("Name"))
    is_default = models.BooleanField(default=False, verbose_name=_("Default profile"))
    company_name = models.CharField(max_length=200, blank=True, verbose_name=_("Company name"))
    footer_text = models.CharField(
        max_length=300, blank=True, default="Confidential – for the customer's internal use only", verbose_name=_("Footer")
    )
    logo = models.ImageField(upload_to="customer-export/logos/", blank=True, verbose_name=_("Logo"))
    primary_color = _color("1F4E79", _("Primary colour"))
    accent_color = _color("2E75B6", _("Accent colour"))
    header_text_color = _color("FFFFFF", _("Table header text"))
    label_bg_color = _color("DEEAF6", _("Label background"))
    stripe_color = _color("F3F7FB", _("Row stripes"))
    font_family = models.CharField(max_length=100, default="Calibri", verbose_name=_("Font"))
    font_size = models.PositiveSmallIntegerField(
        default=10, validators=[MinValueValidator(7), MaxValueValidator(16)], verbose_name=_("Font size (pt)")
    )
    docx_template = models.FileField(
        upload_to="customer-export/templates/",
        blank=True,
        validators=[FileExtensionValidator(["docx", "dotx"])],
        verbose_name=_("Word template"),
    )
    docx_table_style = models.CharField(max_length=100, blank=True, verbose_name=_("Table style (Word)"))
    extra_css = models.TextField(blank=True, verbose_name=_("Additional CSS (PDF/HTML)"))
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-is_default", "name")
        verbose_name = _("branding profile")
        verbose_name_plural = _("branding profiles")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_customer_export:branding_edit", kwargs={"pk": self.pk})

    def save(self, *args, **kwargs):
        for field in ("primary_color", "accent_color", "header_text_color", "label_bg_color", "stripe_color"):
            setattr(self, field, getattr(self, field).lstrip("#").upper())
        super().save(*args, **kwargs)
        if self.is_default:
            BrandingProfile.objects.exclude(pk=self.pk).filter(is_default=True).update(is_default=False)

    def as_branding(self):
        """Dict im Format von branding.DEFAULT_BRANDING."""
        return {
            "name": self.name,
            "company_name": self.company_name,
            "footer_text": self.footer_text,
            "logo_path": self.logo.path if self.logo else None,
            "primary_color": self.primary_color,
            "accent_color": self.accent_color,
            "header_text_color": self.header_text_color,
            "label_bg_color": self.label_bg_color,
            "stripe_color": self.stripe_color,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "docx_template": self.docx_template.path if self.docx_template else None,
            "docx_table_style": self.docx_table_style,
            "extra_css": self.extra_css,
        }


class TopologySymbol(models.Model):
    """Topologie-Symbol für einen Gerätetyp oder eine Geräterolle (Gerätetyp hat Vorrang)."""

    device_type = models.OneToOneField(
        "dcim.DeviceType", on_delete=models.CASCADE, null=True, blank=True, related_name="+", verbose_name=_("Device type")
    )
    role = models.OneToOneField(
        "dcim.DeviceRole", on_delete=models.CASCADE, null=True, blank=True, related_name="+", verbose_name=_("Device role")
    )
    kind = models.CharField(max_length=20, blank=True, verbose_name=_("Symbol"))
    icon = models.ImageField(upload_to="customer-export/symbols/", blank=True, verbose_name=_("Custom icon"))
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("device_type__model", "role__name")
        verbose_name = _("topology symbol")
        verbose_name_plural = _("topology symbols")

    def __str__(self):
        return str(self.device_type or self.role)

    def get_absolute_url(self):
        return reverse("plugins:netbox_customer_export:symbol_edit", kwargs={"pk": self.pk})

    @property
    def target_label(self):
        return _("Device type") if self.device_type_id else _("Device role")

    def get_kind_display(self):
        from .symbols import KIND_CHOICES

        return dict(KIND_CHOICES).get(self.kind, _("Automatic"))

    def clean(self):
        from django.core.exceptions import ValidationError

        if bool(self.device_type_id) == bool(self.role_id):
            raise ValidationError(_("Select exactly one device type or one device role."))
        if not self.kind and not self.icon:
            raise ValidationError(_("Select a symbol or upload a custom icon."))
