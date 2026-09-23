import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dcim", "__first__"),
        ("netbox_customer_export", "0001_brandingprofile"),
    ]

    operations = [
        migrations.CreateModel(
            name="TopologySymbol",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(blank=True, max_length=20, verbose_name="Symbol")),
                ("icon", models.ImageField(blank=True, upload_to="customer-export/symbols/", verbose_name="Eigenes Icon")),
                ("last_updated", models.DateTimeField(auto_now=True)),
                ("device_type", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="+", to="dcim.devicetype", verbose_name="Gerätetyp")),
                ("role", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="+", to="dcim.devicerole", verbose_name="Geräterolle")),
            ],
            options={
                "verbose_name": "Topologie-Symbol",
                "verbose_name_plural": "Topologie-Symbole",
                "ordering": ("device_type__model", "role__name"),
            },
        ),
    ]
