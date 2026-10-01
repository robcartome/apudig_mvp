import datetime
import uuid

from django.db import migrations, models
import django.db.models.deletion


def seed_company_tax_rates(apps, schema_editor):
    Company = apps.get_model("companies", "Company")
    Settings = apps.get_model("companies", "CompanyOperationalSettings")
    TaxRate = apps.get_model("companies", "TaxRate")
    configured = {row.company_id: row.default_igv_rate for row in Settings.objects.all()}
    for company in Company.objects.all().iterator():
        TaxRate.objects.get_or_create(
            company=company,
            code="IGV_GENERAL_PE",
            affectation_type="10",
            valid_from=datetime.date(2000, 1, 1),
            defaults={
                "country_code": "PE",
                "name": "IGV general",
                "rate": configured.get(company.pk, 18),
                "active": True,
                "is_default": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("companies", "0011_companyoperationalsettings_pos_product_search_mode")]

    operations = [
        migrations.CreateModel(
            name="TaxRate",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("country_code", models.CharField(default="PE", max_length=2)),
                ("code", models.CharField(default="IGV_GENERAL_PE", max_length=30)),
                ("name", models.CharField(default="IGV general", max_length=100)),
                ("affectation_type", models.CharField(choices=[("10", "Gravado IGV"), ("20", "Exonerado"), ("30", "Inafecto"), ("40", "Exportacion"), ("11", "Operacion gratuita")], default="10", max_length=5)),
                ("rate", models.DecimalField(decimal_places=2, max_digits=5)),
                ("valid_from", models.DateField()),
                ("valid_until", models.DateField(blank=True, null=True)),
                ("active", models.BooleanField(default=True)),
                ("is_default", models.BooleanField(default=False)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tax_rates", to="companies.company")),
            ],
            options={"db_table": "tax_rates", "ordering": ("-valid_from", "code")},
        ),
        migrations.AddConstraint(model_name="taxrate", constraint=models.UniqueConstraint(fields=("company", "code", "affectation_type", "valid_from"), name="uniq_company_tax_rule_from")),
        migrations.AddConstraint(model_name="taxrate", constraint=models.CheckConstraint(condition=models.Q(("rate__gte", 0)), name="tax_rate_gte_zero")),
        migrations.AddConstraint(model_name="taxrate", constraint=models.CheckConstraint(condition=models.Q(("valid_until__isnull", True), ("valid_until__gte", models.F("valid_from")), _connector="OR"), name="tax_rate_valid_period")),
        migrations.AddConstraint(model_name="taxrate", constraint=models.UniqueConstraint(condition=models.Q(("active", True), ("is_default", True), ("valid_until__isnull", True)), fields=("company", "affectation_type"), name="uniq_current_default_tax_affectation")),
        migrations.RunPython(seed_company_tax_rates, migrations.RunPython.noop),
    ]
