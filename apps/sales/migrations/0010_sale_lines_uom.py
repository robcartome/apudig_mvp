from django.db import migrations, models
import django.db.models.deletion


LINE_MODELS = ("SalesQuotationLine", "SaleOrderLine", "SalesDocumentLine")


def initialize_line_units(apps, schema_editor):
    for model_name in LINE_MODELS:
        Line = apps.get_model("sales", model_name)
        for line in Line.objects.select_related("product").iterator():
            line.unit_id = line.product.unit_id
            line.unit_code = line.product.unit.code
            line.conversion_factor = 1
            line.stock_quantity = line.quantity
            line.save(update_fields=("unit", "unit_code", "conversion_factor", "stock_quantity"))


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0010_product_units_and_movement_uom"),
        ("sales", "0009_salesdocumentline_memo"),
    ]

    operations = [
        *[
            operation
            for model_name in ("salesquotationline", "saleorderline", "salesdocumentline")
            for operation in (
                migrations.AddField(model_name=model_name, name="unit", field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="inventory.unit")),
                migrations.AddField(model_name=model_name, name="conversion_factor", field=models.DecimalField(decimal_places=6, default=1, max_digits=18)),
                migrations.AddField(model_name=model_name, name="stock_quantity", field=models.DecimalField(decimal_places=6, default=0, max_digits=18)),
            )
        ],
        migrations.RunPython(initialize_line_units, migrations.RunPython.noop),
        *[
            migrations.AlterField(
                model_name=model_name,
                name="unit",
                field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="inventory.unit"),
            )
            for model_name in ("salesquotationline", "saleorderline", "salesdocumentline")
        ],
    ]
