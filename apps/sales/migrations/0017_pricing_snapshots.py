from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0020_pricing_tax_and_cost_fields"),
        ("sales", "0016_payment_method_operational_options"),
    ]

    operations = [
        migrations.AlterField(model_name="salesquotationline", name="igv_rate", field=models.DecimalField(decimal_places=2, default=0, max_digits=5)),
        migrations.AlterField(model_name="saleorderline", name="igv_rate", field=models.DecimalField(decimal_places=2, default=0, max_digits=5)),
        migrations.AlterField(model_name="salesdocumentline", name="igv_rate", field=models.DecimalField(decimal_places=2, default=0, max_digits=5)),
        migrations.AddField(model_name="salesquotation", name="price_list", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="quotations", to="inventory.pricelist")),
        migrations.AddField(model_name="salesdocumentline", name="global_discount_amount", field=models.DecimalField(decimal_places=2, default=0, max_digits=14)),
    ]
