import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("treasury", "0016_bank_transfers_reversals_and_sequences")]

    operations = [
        migrations.AlterField(
            model_name="bankreconciliationmatch",
            name="statement_line",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="reconciliation_matches",
                to="treasury.bankstatementline",
            ),
        ),
        migrations.AddConstraint(
            model_name="bankreconciliationmatch",
            constraint=models.UniqueConstraint(
                fields=("statement_line", "bank_movement"),
                name="uniq_treasury_reconciliation_line_movement",
            ),
        ),
    ]
