# Generated manually — scope masters (Category, Brand, Product, PriceList) to Company

import django.db.models.deletion
from django.db import migrations, models


def assign_existing_to_first_company(apps, schema_editor):
    """Assign all existing Category / Brand / PriceList / Product records
    to the first Company found (ordered by creation date).
    Safe to run on fresh DBs (no-op when no rows exist).
    """
    Company = apps.get_model("companies", "Company")
    first_company = Company.objects.order_by("created_at").first()
    if first_company is None:
        return  # No companies yet — nothing to migrate

    for ModelName in ("Category", "Brand", "PriceList", "Product"):
        Model = apps.get_model("inventory", ModelName)
        Model.objects.filter(company__isnull=True).update(company=first_company)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0001_initial"),
        ("inventory", "0006_movement_closed_at_movement_closed_by_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="categories",
                to="companies.company",
            ),
        ),
        migrations.AddField(
            model_name="brand",
            name="company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="brands",
                to="companies.company",
            ),
        ),
        migrations.AddField(
            model_name="pricelist",
            name="company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="price_lists",
                to="companies.company",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="products",
                to="companies.company",
            ),
        ),

        migrations.RunPython(assign_existing_to_first_company, noop_reverse),

        migrations.AlterField(
            model_name="category",
            name="code",
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name="brand",
            name="name",
            field=models.CharField(max_length=255),
        ),
        migrations.AlterField(
            model_name="product",
            name="sku",
            field=models.CharField(max_length=100),
        ),

        migrations.AlterUniqueTogether(
            name="category",
            unique_together={("company", "code")},
        ),
        migrations.AlterUniqueTogether(
            name="brand",
            unique_together={("company", "name")},
        ),
        migrations.AlterUniqueTogether(
            name="product",
            unique_together={("company", "sku")},
        ),
    ]
