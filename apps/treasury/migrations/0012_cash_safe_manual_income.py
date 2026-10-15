from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("treasury", "0011_cash_safe_deposit_tracking")]
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
                    ("ADJUSTMENT", "Ajuste autorizado"),
                ],
                max_length=30,
            ),
        ),
    ]
