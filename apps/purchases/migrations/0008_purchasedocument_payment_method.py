import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0007_purchaselandedcost_purchaselandedcostallocation_and_more"),
        ("sales", "0010_sale_lines_uom"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasedocument",
            name="payment_method",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="purchase_documents",
                to="sales.paymentmethod",
                verbose_name="Condicion de pago",
            ),
        ),
    ]
