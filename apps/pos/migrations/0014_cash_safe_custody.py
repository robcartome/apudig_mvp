import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


CODE = "manage.pos.cash_safe"


def seed_permission(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Role = apps.get_model("users", "Role")
    RolePermission = apps.get_model("users", "RolePermission")
    permission, _ = Permission.objects.update_or_create(
        code=CODE,
        defaults={
            "action_name": "manage", "module": "pos.cash_safe",
            "description": "Gestionar ingresos y retiros de caja fuerte",
        },
    )
    for role in Role.objects.filter(name__in=("ADMIN", "SUPERUSER")):
        RolePermission.objects.get_or_create(role=role, permission=permission)


def unseed_permission(apps, schema_editor):
    apps.get_model("users", "Permission").objects.filter(code=CODE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0013_seed_pos_product_create_permission"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="cashsession", name="safe_deposit_total",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="cashsession", name="bank_deposit_total",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="cashsession", name="bank_deposit_destination",
            field=models.CharField(blank=True, max_length=200),
        ),
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
            options={"db_table": "pos_cash_safe_movements", "ordering": ("-created_at",)},
        ),
        migrations.AddConstraint(
            model_name="cashsafemovement",
            constraint=models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="cash_safe_movement_amount_gt_zero"),
        ),
        migrations.RunPython(seed_permission, unseed_permission),
    ]
