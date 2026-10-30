from django.db import migrations


CODE = "correct.pos.payment"


def seed_permission(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Role = apps.get_model("users", "Role")
    RolePermission = apps.get_model("users", "RolePermission")
    permission, _ = Permission.objects.update_or_create(
        code=CODE,
        defaults={
            "action_name": "correct",
            "module": "pos.payment",
            "description": "Corregir medios de pago de ventas POS emitidas",
        },
    )
    for role in Role.objects.filter(name__in=("ADMIN", "SUPERUSER")):
        RolePermission.objects.get_or_create(role=role, permission=permission)


def unseed_permission(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Permission.objects.filter(code=CODE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0017_cashsession_bank_deposit_account"),
        ("users", "0005_useroperationalflags_can_correct_pos_payment"),
    ]

    operations = [migrations.RunPython(seed_permission, unseed_permission)]
