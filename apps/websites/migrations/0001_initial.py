# Generated for APUDIG storefront tenant isolation.
import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("companies", "0015_companybranding_show_company_name_with_logo"),
    ]
    operations = [
        migrations.CreateModel(
            name="Website",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("status", models.CharField(choices=[("DRAFT", "Borrador"), ("PUBLISHED", "Publicado"), ("SUSPENDED", "Suspendido")], default="DRAFT", max_length=20)),
                ("company", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="website", to="companies.company")),
            ],
            options={"db_table": "websites", "ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="WebsiteDomain",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("hostname", models.CharField(max_length=253, unique=True)),
                ("status", models.CharField(choices=[("PENDING", "Pendiente"), ("VERIFIED", "Verificado"), ("ACTIVE", "Activo"), ("DISABLED", "Deshabilitado")], default="PENDING", max_length=20)),
                ("is_primary", models.BooleanField(default=False)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("website", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="domains", to="websites.website")),
            ],
            options={"db_table": "website_domains", "ordering": ("hostname",)},
        ),
        migrations.AddConstraint(
            model_name="websitedomain",
            constraint=models.UniqueConstraint(condition=models.Q(("is_primary", True)), fields=("website",), name="uniq_primary_domain_per_website"),
        ),
    ]
