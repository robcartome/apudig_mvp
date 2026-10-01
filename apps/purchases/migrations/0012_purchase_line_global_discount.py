from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("purchases", "0011_purchasedocument_price_history_index")]

    operations = [
        migrations.AlterField(model_name="purchaseorderline", name="igv_rate", field=models.DecimalField(decimal_places=2, default=0, max_digits=5)),
        migrations.AlterField(model_name="purchasedocumentline", name="igv_rate", field=models.DecimalField(decimal_places=2, default=0, max_digits=5)),
        migrations.AddField(model_name="purchasedocumentline", name="global_discount_amount", field=models.DecimalField(decimal_places=2, default=0, max_digits=14)),
    ]
