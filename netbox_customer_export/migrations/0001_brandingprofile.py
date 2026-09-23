import django.core.validators
from django.db import migrations, models

HEX = django.core.validators.RegexValidator("^[0-9A-Fa-f]{6}$", "Hex-Farbe ohne # erwartet, z.B. 1F4E79")


def color(default, verbose_name):
    return models.CharField(default=default, max_length=6, validators=[HEX], verbose_name=verbose_name)


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="BrandingProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True, verbose_name="Name")),
                ("is_default", models.BooleanField(default=False, verbose_name="Standardprofil")),
                ("company_name", models.CharField(blank=True, max_length=200, verbose_name="Firmenname")),
                ("footer_text", models.CharField(blank=True, default="Vertraulich – nur für den internen Gebrauch des Kunden", max_length=300, verbose_name="Fußzeile")),
                ("logo", models.ImageField(blank=True, upload_to="customer-export/logos/", verbose_name="Logo")),
                ("primary_color", color("1F4E79", "Primärfarbe")),
                ("accent_color", color("2E75B6", "Akzentfarbe")),
                ("header_text_color", color("FFFFFF", "Schrift Tabellenkopf")),
                ("label_bg_color", color("DEEAF6", "Hintergrund Beschriftungen")),
                ("stripe_color", color("F3F7FB", "Zebrastreifen")),
                ("font_family", models.CharField(default="Calibri", max_length=100, verbose_name="Schriftart")),
                ("font_size", models.PositiveSmallIntegerField(default=10, validators=[django.core.validators.MinValueValidator(7), django.core.validators.MaxValueValidator(16)], verbose_name="Schriftgröße (pt)")),
                ("docx_template", models.FileField(blank=True, upload_to="customer-export/templates/", validators=[django.core.validators.FileExtensionValidator(["docx", "dotx"])], verbose_name="Word-Vorlage")),
                ("docx_table_style", models.CharField(blank=True, max_length=100, verbose_name="Tabellenformatvorlage (Word)")),
                ("extra_css", models.TextField(blank=True, verbose_name="Zusätzliches CSS (PDF/HTML)")),
                ("last_updated", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Branding-Profil",
                "verbose_name_plural": "Branding-Profile",
                "ordering": ("-is_default", "name"),
            },
        ),
    ]
