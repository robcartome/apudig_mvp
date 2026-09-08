from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0009_purchase_document_receipt_matching"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasedocument",
            name="global_discount_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="purchasedocument",
            name="global_discount_before_tax",
            field=models.BooleanField(default=False),
        ),
        migrations.AddConstraint(
            model_name="purchasedocument",
            constraint=models.CheckConstraint(
                condition=models.Q(global_discount_amount__gte=0),
                name="purchase_document_global_discount_gte_zero",
            ),
        ),
    ]
