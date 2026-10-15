from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("pos", "0015_cashmovement_payment_details")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[migrations.DeleteModel(name="CashSafeMovement")],
        )
    ]
