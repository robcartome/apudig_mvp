from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("treasury", "0017_grouped_bank_reconciliation")]

    operations = [
        migrations.AlterField(
            model_name="cashsafedeposit",
            name="status",
            field=models.CharField(
                choices=[
                    ("REQUESTED", "Pendiente de entrega"),
                    ("IN_TRANSIT", "En tránsito"),
                    ("DEPOSITED", "Depositado"),
                    ("CANCELLED", "Cancelado"),
                    ("REVERSED", "Revertido"),
                ], default="REQUESTED", max_length=12,
            ),
        ),
    ]
