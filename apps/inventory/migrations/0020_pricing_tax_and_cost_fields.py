from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations, models


def prepare_existing_pricing(apps, schema_editor):
    PriceList = apps.get_model("inventory", "PriceList")
    Product = apps.get_model("inventory", "Product")
    Settings = apps.get_model("companies", "CompanyOperationalSettings")

    for company_id in PriceList.objects.exclude(company_id=None).values_list("company_id", flat=True).distinct():
        seen = set()
        default_seen = False
        for price_list in PriceList.objects.filter(company_id=company_id).order_by("created_at", "pk"):
            base_name = price_list.name
            candidate = base_name
            suffix = 2
            while candidate.casefold() in seen:
                candidate = f"{base_name} ({suffix})"
                suffix += 1
            seen.add(candidate.casefold())
            changes = []
            if candidate != price_list.name:
                price_list.name = candidate
                changes.append("name")
            if price_list.is_default:
                if default_seen:
                    price_list.is_default = False
                    changes.append("is_default")
                default_seen = True
            if changes:
                price_list.save(update_fields=changes)

    rates = dict(Settings.objects.values_list("company_id", "default_igv_rate"))
    quantum = Decimal("0.000001")
    for product in Product.objects.all().iterator():
        commercial = Decimal(str(product.price_purchase or 0))
        rate = Decimal(str(rates.get(product.company_id, Decimal("18"))))
        net = commercial
        if product.tax_affectation == "10" and rate:
            net = commercial / (Decimal("1") + rate / Decimal("100"))
        product.last_purchase_unit_value = net.quantize(quantum, rounding=ROUND_HALF_UP)
        product.inventory_unit_cost = product.last_purchase_unit_value
        product.save(update_fields=("last_purchase_unit_value", "inventory_unit_cost"))


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("companies", "0012_taxrate"),
        ("inventory", "0019_movement_sales_document"),
    ]

    operations = [
        migrations.AddField(model_name="pricelist", name="prices_include_tax", field=models.BooleanField(default=True, help_text="Los importes de esta lista son precios comerciales finales.")),
        migrations.AddField(model_name="product", name="tax_affectation", field=models.CharField(choices=[("10", "Gravado IGV"), ("20", "Exonerado"), ("30", "Inafecto"), ("40", "Exportacion"), ("11", "Operacion gratuita")], default="10", max_length=5)),
        migrations.AddField(model_name="product", name="last_purchase_unit_value", field=models.DecimalField(decimal_places=6, default=0, max_digits=14)),
        migrations.AddField(model_name="product", name="inventory_unit_cost", field=models.DecimalField(decimal_places=6, default=0, max_digits=14)),
        migrations.AlterField(model_name="movementdetail", name="unit_price", field=models.DecimalField(decimal_places=6, default=0, help_text="Costo unitario de inventario en moneda base; nunca precio de venta.", max_digits=14)),
        migrations.AddField(model_name="movementdetail", name="cost_source", field=models.CharField(choices=[("LEGACY", "Historico sin clasificar"), ("MANUAL", "Manual"), ("PURCHASE", "Compra"), ("AVERAGE", "Costo promedio")], default="LEGACY", max_length=10)),
        migrations.RunPython(prepare_existing_pricing, noop_reverse),
        migrations.AlterField(model_name="movementdetail", name="cost_source", field=models.CharField(choices=[("LEGACY", "Historico sin clasificar"), ("MANUAL", "Manual"), ("PURCHASE", "Compra"), ("AVERAGE", "Costo promedio")], default="MANUAL", max_length=10)),
        migrations.AddConstraint(model_name="pricelist", constraint=models.UniqueConstraint(fields=("company", "name"), name="uniq_company_price_list_name")),
        migrations.AddConstraint(model_name="pricelist", constraint=models.UniqueConstraint(condition=models.Q(("is_default", True)), fields=("company",), name="uniq_default_price_list_per_company")),
    ]
