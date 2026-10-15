import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0017_cashsession_bank_deposit_account"),
        ("treasury", "0018_cash_safe_deposit_reversed_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="cashsafemovement",
            name="destination_register",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cash_safe_transfers_received",
                to="pos.posregister",
            ),
        ),
    ]
