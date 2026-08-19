import uuid

from django.db import migrations, models
import django.db.models.deletion


def initialize_product_units(apps, schema_editor):
    Product = apps.get_model("inventory", "Product")
    ProductUnit = apps.get_model("inventory", "ProductUnit")
    MovementDetail = apps.get_model("inventory", "MovementDetail")
    for product in Product.objects.exclude(unit_id=None).iterator():
        ProductUnit.objects.get_or_create(
            product_id=product.pk,
            unit_id=product.unit_id,
            defaults={
                "conversion_factor": 1,
                "is_default_sale": True,
                "is_default_purchase": True,
                "active": True,
            },
        )
    for detail in MovementDetail.objects.select_related("product").iterator():
        detail.unit_id = detail.product.unit_id
        detail.unit_code = detail.product.unit.code
        detail.conversion_factor = 1
        detail.stock_quantity = detail.quantity
        detail.save(update_fields=("unit", "unit_code", "conversion_factor", "stock_quantity"))


class Migration(migrations.Migration):
    dependencies = [("inventory", "0009_movement_origin_movement_reversal_of_and_more")]

    operations = [
        migrations.CreateModel(
            name="ProductUnit",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("conversion_factor", models.DecimalField(decimal_places=6, default=1, max_digits=18)),
                ("sale_price", models.DecimalField(blank=True, decimal_places=6, max_digits=14, null=True)),
                ("purchase_price", models.DecimalField(blank=True, decimal_places=6, max_digits=14, null=True)),
                ("is_default_sale", models.BooleanField(default=False)),
                ("is_default_purchase", models.BooleanField(default=False)),
                ("active", models.BooleanField(default=True)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="unit_conversions", to="inventory.product")),
                ("unit", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="product_conversions", to="inventory.unit")),
            ],
            options={"db_table": "product_units", "ordering": ["unit__code"]},
        ),
        migrations.AddConstraint(
            model_name="productunit",
            constraint=models.UniqueConstraint(fields=("product", "unit"), name="uniq_product_unit"),
        ),
        migrations.AddConstraint(
            model_name="productunit",
            constraint=models.CheckConstraint(condition=models.Q(conversion_factor__gt=0), name="product_unit_factor_gt_zero"),
        ),
        migrations.AddConstraint(
            model_name="productunit",
            constraint=models.UniqueConstraint(condition=models.Q(is_default_sale=True), fields=("product",), name="uniq_product_default_sale_unit"),
        ),
        migrations.AddConstraint(
            model_name="productunit",
            constraint=models.UniqueConstraint(condition=models.Q(is_default_purchase=True), fields=("product",), name="uniq_product_default_purchase_unit"),
        ),
        migrations.AddField(model_name="movementdetail", name="unit", field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="movement_details", to="inventory.unit")),
        migrations.AddField(model_name="movementdetail", name="unit_code", field=models.CharField(default="NIU", max_length=10)),
        migrations.AddField(model_name="movementdetail", name="conversion_factor", field=models.DecimalField(decimal_places=6, default=1, max_digits=18)),
        migrations.AddField(model_name="movementdetail", name="stock_quantity", field=models.DecimalField(decimal_places=6, default=0, max_digits=18)),
        migrations.RunPython(initialize_product_units, migrations.RunPython.noop),
        migrations.AlterField(model_name="movementdetail", name="unit", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="movement_details", to="inventory.unit")),
    ]
