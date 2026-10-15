import django.db.models.deletion
from django.db import migrations, models


def backfill_sequences(apps, schema_editor):
    CashSafeMovement = apps.get_model("treasury", "CashSafeMovement")
    BankMovement = apps.get_model("treasury", "BankMovement")
    for model, prefix in ((CashSafeMovement, "CF"), (BankMovement, "BM")):
        counters = {}
        for movement in model.objects.order_by("company_id", "created_at", "id").iterator():
            local_date = movement.created_at.date()
            key = (movement.company_id, local_date.year, local_date.month)
            counters[key] = counters.get(key, 0) + 1
            movement.sequence_number = counters[key]
            movement.movement_number = (
                f"{prefix}-{local_date:%Y%m}-{movement.sequence_number:06d}"
            )
            movement.save(update_fields=("sequence_number", "movement_number"))


def remove_legacy_pos_permission(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Permission.objects.filter(code="manage.pos.cash_safe").delete()


class Migration(migrations.Migration):
    dependencies = [("treasury", "0015_cash_safe_fund_transfers")]

    operations = [
        migrations.AddField(
            model_name="bankmovement",
            name="destination_account",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="incoming_transfer_requests", to="treasury.bankaccount",
            ),
        ),
        migrations.AddField(
            model_name="bankmovement",
            name="transfer_source",
            field=models.OneToOneField(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="transfer_destination_movement", to="treasury.bankmovement",
            ),
        ),
        migrations.AddField(
            model_name="bankmovement", name="sequence_number",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="bankmovement", name="reversed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bankmovement", name="reversal_reason",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="bankmovement", name="reversed_movement",
            field=models.OneToOneField(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="reversal", to="treasury.bankmovement",
            ),
        ),
        migrations.AlterField(
            model_name="bankmovement", name="status",
            field=models.CharField(
                choices=[
                    ("POSTED", "Confirmado"), ("VOIDED", "Anulado"),
                    ("REVERSED", "Revertido"),
                ], default="POSTED", max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="cashsafemovement", name="sequence_number",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.RunPython(backfill_sequences, migrations.RunPython.noop),
        migrations.RunPython(remove_legacy_pos_permission, migrations.RunPython.noop),
    ]
