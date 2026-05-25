# Generated manually - scope partners masters to Company

import django.db.models.deletion
from django.db import migrations, models


def assign_existing_to_first_company(apps, schema_editor):
    Company = apps.get_model("companies", "Company")
    first_company = Company.objects.order_by("created_at").first()
    if first_company is None:
        return

    for model_name in ("CoreCustomer", "Supplier", "Carrier"):
        Model = apps.get_model("partners", model_name)
        Model.objects.filter(company__isnull=True).update(company=first_company)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0001_initial"),
        ("partners", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="corecustomer",
            name="company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="customers",
                to="companies.company",
            ),
        ),
        migrations.AddField(
            model_name="supplier",
            name="company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="suppliers",
                to="companies.company",
            ),
        ),
        migrations.AddField(
            model_name="carrier",
            name="company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="carriers",
                to="companies.company",
            ),
        ),
        migrations.RunPython(assign_existing_to_first_company, noop_reverse),
        migrations.AlterField(
            model_name="supplier",
            name="document_number",
            field=models.CharField(max_length=20),
        ),
        migrations.AlterUniqueTogether(
            name="corecustomer",
            unique_together={("company", "document_type", "document_number")},
        ),
        migrations.AlterUniqueTogether(
            name="supplier",
            unique_together={("company", "document_number")},
        ),
        migrations.AlterUniqueTogether(
            name="carrier",
            unique_together={("company", "document_number")},
        ),
    ]
