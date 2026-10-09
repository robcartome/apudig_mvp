from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0014_cash_safe_custody"),
        ("sales", "0017_pricing_snapshots"),
    ]

    operations = [
        migrations.AddField(
            model_name="cashmovement",
            name="means_of_payment",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cash_movements",
                to="sales.meansofpayment",
            ),
        ),
        migrations.AddField(
            model_name="cashmovement",
            name="operation_reference",
            field=models.CharField(blank=True, max_length=120),
        ),
    ]
