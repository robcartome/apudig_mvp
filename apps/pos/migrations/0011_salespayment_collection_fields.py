from django.db import migrations, models


PERMISSION_CODE = "manage.pos.collections"


def seed_permission(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Role = apps.get_model("users", "Role")
    RolePermission = apps.get_model("users", "RolePermission")
    permission, _ = Permission.objects.update_or_create(
        code=PERMISSION_CODE,
        defaults={
            "action_name": "manage",
            "module": "pos.collections",
            "description": "Registrar cobranzas de ventas a credito",
        },
    )
    for role in Role.objects.filter(name__in=("ADMIN", "SUPERUSER", "CASHIER")):
        RolePermission.objects.get_or_create(role=role, permission=permission)


def unseed_permission(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Permission.objects.filter(code=PERMISSION_CODE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0010_seed_cash_movement_authorization_permission"),
        ("users", "0004_alter_permission_action_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="salespayment",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("SALE_CHECKOUT", "Pago durante la venta"),
                    ("CREDIT_COLLECTION", "Cobranza de credito"),
                ],
                default="SALE_CHECKOUT",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="salespayment",
            name="idempotency_key",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="salespayment",
            constraint=models.UniqueConstraint(
                condition=models.Q(idempotency_key__isnull=False),
                fields=("cash_session", "idempotency_key"),
                name="uniq_pos_payment_session_idempotency",
            ),
        ),
        migrations.RunPython(seed_permission, unseed_permission),
    ]
