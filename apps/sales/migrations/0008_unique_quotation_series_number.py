from django.db import migrations, models


def ensure_no_duplicate_quotations(apps, schema_editor):
    SalesQuotation = apps.get_model("sales", "SalesQuotation")
    duplicates = (
        SalesQuotation.objects.exclude(number__isnull=True)
        .values("series_id", "number")
        .annotate(total=models.Count("id"))
        .filter(total__gt=1)
        .first()
    )
    if duplicates:
        raise RuntimeError(
            "No se puede crear la restricción única: existen cotizaciones "
            f"duplicadas para serie={duplicates['series_id']} y número={duplicates['number']}."
        )


class Migration(migrations.Migration):
    dependencies = [("sales", "0007_unify_document_types")]

    operations = [
        migrations.RunPython(ensure_no_duplicate_quotations, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="salesquotation",
            constraint=models.UniqueConstraint(
                fields=("series", "number"),
                condition=models.Q(number__isnull=False),
                name="uniq_sales_quotation_series_number",
            ),
        ),
    ]
