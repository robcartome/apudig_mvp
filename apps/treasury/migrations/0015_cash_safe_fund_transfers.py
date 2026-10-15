import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("treasury", "0014_treasury_funds")]

    operations = [
        migrations.AlterField(
            model_name="cashsafemovement",
            name="movement_type",
            field=models.CharField(
                choices=[
                    ("CLOSING_DEPOSIT", "Guardado desde cierre de caja"),
                    ("MANUAL_INCOME", "Ingreso manual o reposición"),
                    ("BANK_DEPOSIT", "Entrega para depósito bancario"),
                    ("OWNER_HANDOVER", "Entrega a dueño o administrador"),
                    ("CASH_PAYMENT", "Pago en efectivo"),
                    ("DRAWER_TRANSFER", "Transferencia a gaveta"),
                    ("FUND_TRANSFER", "Transferencia entre fondos"),
                    ("ADJUSTMENT", "Ajuste autorizado"),
                ],
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="cashsafemovement",
            name="destination_fund",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="incoming_transfer_requests", to="treasury.treasuryfund",
            ),
        ),
        migrations.AddField(
            model_name="cashsafemovement",
            name="transfer_source",
            field=models.OneToOneField(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="transfer_destination_movement", to="treasury.cashsafemovement",
            ),
        ),
    ]
