import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q
from django.utils import timezone


def backfill_numbers(apps, schema_editor):
    Movement = apps.get_model("treasury", "CashSafeMovement")
    for movement in Movement.objects.filter(movement_number="").iterator():
        date = movement.created_at or timezone.now()
        movement.movement_number = f"CF-{date:%Y%m}-{str(movement.pk)[:8].upper()}"
        movement.save(update_fields=("movement_number",))


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("treasury", "0001_seed_treasury_permissions"),
        ("pos", "0016_transfer_cash_safe_to_treasury"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="CashSafeMovement",
                    fields=[
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("direction", models.CharField(choices=[("IN", "Ingreso"), ("OUT", "Salida")], max_length=3)),
                        ("movement_type", models.CharField(choices=[("CLOSING_DEPOSIT", "Guardado desde cierre de caja"), ("BANK_DEPOSIT", "Entrega para depósito bancario"), ("OWNER_HANDOVER", "Entrega a dueño o administrador"), ("CASH_PAYMENT", "Pago en efectivo"), ("DRAWER_TRANSFER", "Transferencia a gaveta"), ("ADJUSTMENT", "Ajuste autorizado")], max_length=30)),
                        ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                        ("currency", models.CharField(choices=[("PEN", "Soles"), ("USD", "Dólares")], default="PEN", max_length=3)),
                        ("recipient_name", models.CharField(blank=True, max_length=200)),
                        ("destination", models.CharField(blank=True, max_length=200)),
                        ("reference", models.CharField(blank=True, max_length=120)),
                        ("notes", models.CharField(blank=True, max_length=500)),
                        ("authorized_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="authorized_cash_safe_movements", to=settings.AUTH_USER_MODEL)),
                        ("cash_session", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="safe_movements", to="pos.cashsession")),
                        ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cash_safe_movements", to="companies.company")),
                        ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_cash_safe_movements", to=settings.AUTH_USER_MODEL)),
                        ("store", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cash_safe_movements", to="companies.store")),
                    ],
                    options={
                        "db_table": "pos_cash_safe_movements",
                        "ordering": ("-created_at",),
                        "constraints": [models.CheckConstraint(condition=Q(amount__gt=0), name="cash_safe_movement_amount_gt_zero")],
                    },
                )
            ],
        ),
        migrations.AddField(model_name="cashsafemovement", name="movement_number", field=models.CharField(blank=True, default="", max_length=30), preserve_default=False),
        migrations.AddField(model_name="cashsafemovement", name="status", field=models.CharField(choices=[("PENDING", "Pendiente de aprobación"), ("POSTED", "Confirmado"), ("REJECTED", "Rechazado"), ("REVERSED", "Revertido")], default="POSTED", max_length=10)),
        migrations.AddField(model_name="cashsafemovement", name="reversed_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="cashsafemovement", name="reversal_reason", field=models.CharField(blank=True, max_length=500)),
        migrations.AddField(model_name="cashsafemovement", name="reversed_movement", field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reversal", to="treasury.cashsafemovement")),
        migrations.RunPython(backfill_numbers, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="cashsafemovement",
            constraint=models.UniqueConstraint(condition=~Q(movement_number=""), fields=("company", "movement_number"), name="uniq_cash_safe_movement_number"),
        ),
    ]
