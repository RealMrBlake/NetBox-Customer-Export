from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.urls import reverse

hex_color = RegexValidator(r"^[0-9A-Fa-f]{6}$", "Hex-Farbe ohne # erwartet, z.B. 1F4E79")


def _color(default, verbose_name):
    return models.CharField(max_length=6, default=default, validators=[hex_color], verbose_name=verbose_name)


class BrandingProfile(models.Model):
    """In NetBox gepflegtes Design-Profil (Alternative/Ergänzung zu PLUGINS_CONFIG['brandings'])."""

    name = models.CharField(max_length=100, unique=True, verbose_name="Name")
    is_default = models.BooleanField(default=False, verbose_name="Standardprofil")
    company_name = models.CharField(max_length=200, blank=True, verbose_name="Firmenname")
    footer_text = models.CharField(
        max_length=300, blank=True, default="Vertraulich – nur für den internen Gebrauch des Kunden", verbose_name="Fußzeile"
    )
    logo = models.ImageField(upload_to="customer-export/logos/", blank=True, verbose_name="Logo")
    primary_color = _color("1F4E79", "Primärfarbe")
    accent_color = _color("2E75B6", "Akzentfarbe")
    header_text_color = _color("FFFFFF", "Schrift Tabellenkopf")
    label_bg_color = _color("DEEAF6", "Hintergrund Beschriftungen")
    stripe_color = _color("F3F7FB", "Zebrastreifen")
    font_family = models.CharField(max_length=100, default="Calibri", verbose_name="Schriftart")
    font_size = models.PositiveSmallIntegerField(
        default=10, validators=[MinValueValidator(7), MaxValueValidator(16)], verbose_name="Schriftgröße (pt)"
    )
    docx_template = models.FileField(
        upload_to="customer-export/templates/",
        blank=True,
        validators=[FileExtensionValidator(["docx", "dotx"])],
        verbose_name="Word-Vorlage",
    )
    docx_table_style = models.CharField(max_length=100, blank=True, verbose_name="Tabellenformatvorlage (Word)")
    extra_css = models.TextField(blank=True, verbose_name="Zusätzliches CSS (PDF/HTML)")
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-is_default", "name")
        verbose_name = "Branding-Profil"
        verbose_name_plural = "Branding-Profile"

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
        "dcim.DeviceType", on_delete=models.CASCADE, null=True, blank=True, related_name="+", verbose_name="Gerätetyp"
    )
    role = models.OneToOneField(
        "dcim.DeviceRole", on_delete=models.CASCADE, null=True, blank=True, related_name="+", verbose_name="Geräterolle"
    )
    kind = models.CharField(max_length=20, blank=True, verbose_name="Symbol")
    icon = models.ImageField(upload_to="customer-export/symbols/", blank=True, verbose_name="Eigenes Icon")
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("device_type__model", "role__name")
        verbose_name = "Topologie-Symbol"
        verbose_name_plural = "Topologie-Symbole"

    def __str__(self):
        return str(self.device_type or self.role)

    def get_absolute_url(self):
        return reverse("plugins:netbox_customer_export:symbol_edit", kwargs={"pk": self.pk})

    @property
    def target_label(self):
        return "Gerätetyp" if self.device_type_id else "Geräterolle"

    def get_kind_display(self):
        from .symbols import KIND_CHOICES

        return dict(KIND_CHOICES).get(self.kind, "Automatisch")

    def clean(self):
        from django.core.exceptions import ValidationError

        if bool(self.device_type_id) == bool(self.role_id):
            raise ValidationError("Bitte genau einen Gerätetyp oder eine Geräterolle wählen.")
        if not self.kind and not self.icon:
            raise ValidationError("Bitte ein Symbol wählen oder ein eigenes Icon hochladen.")
