import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0016_transfer_cash_safe_to_treasury"),
        ("treasury", "0016_bank_transfers_reversals_and_sequences"),
    ]

    operations = [
        migrations.AddField(
            model_name="cashsession",
            name="bank_deposit_account",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="direct_pos_cash_deposits", to="treasury.bankaccount",
            ),
        ),
    ]
