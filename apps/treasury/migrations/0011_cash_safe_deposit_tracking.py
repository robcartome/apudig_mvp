import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def backfill_deposits(apps, schema_editor):
    CashSafeMovement = apps.get_model("treasury", "CashSafeMovement")
    CashSafeDeposit = apps.get_model("treasury", "CashSafeDeposit")
    BankMovement = apps.get_model("treasury", "BankMovement")
    for movement in CashSafeMovement.objects.filter(
        movement_type="BANK_DEPOSIT", bank_account__isnull=False
    ).iterator():
        bank_movement = BankMovement.objects.filter(safe_movement=movement).first()
        if bank_movement:
            status = "DEPOSITED"
            operation_date = bank_movement.operation_date
            operation_reference = bank_movement.reference
            deposited_at = bank_movement.created_at
            deposited_by_id = bank_movement.created_by_id
        elif movement.status == "POSTED":
            status = "IN_TRANSIT"
            operation_date = None
            operation_reference = ""
            deposited_at = None
            deposited_by_id = None
        elif movement.status in ("REJECTED", "REVERSED"):
            status = "CANCELLED"
            operation_date = None
            operation_reference = ""
            deposited_at = None
            deposited_by_id = None
        else:
            status = "REQUESTED"
            operation_date = None
            operation_reference = ""
            deposited_at = None
            deposited_by_id = None
        CashSafeDeposit.objects.create(
            cash_movement=movement,
            account_id=movement.bank_account_id,
            status=status,
            handed_over_by_id=(
                movement.authorized_by_id if status in ("IN_TRANSIT", "DEPOSITED") else None
            ),
            handed_over_at=(
                movement.authorized_at if status in ("IN_TRANSIT", "DEPOSITED") else None
            ),
            deposited_by_id=deposited_by_id,
            deposited_at=deposited_at,
            operation_date=operation_date,
            operation_reference=operation_reference,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("treasury", "0010_cash_safe_count_sequence"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="CashSafeDeposit",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("REQUESTED", "Pendiente de entrega"), ("IN_TRANSIT", "En tránsito"), ("DEPOSITED", "Depositado"), ("CANCELLED", "Cancelado")], default="REQUESTED", max_length=12)),
                ("handed_over_at", models.DateTimeField(blank=True, null=True)),
                ("deposited_at", models.DateTimeField(blank=True, null=True)),
                ("operation_date", models.DateField(blank=True, null=True)),
                ("operation_reference", models.CharField(blank=True, max_length=120)),
                ("confirmation_notes", models.CharField(blank=True, max_length=500)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cash_safe_deposits", to="treasury.bankaccount")),
                ("cash_movement", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="deposit_tracking", to="treasury.cashsafemovement")),
                ("deposited_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="confirmed_cash_safe_deposits", to=settings.AUTH_USER_MODEL)),
                ("handed_over_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="handed_over_cash_safe_deposits", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "treasury_cash_safe_deposits", "ordering": ("-created_at",)},
        ),
        migrations.RunPython(backfill_deposits, migrations.RunPython.noop),
    ]
