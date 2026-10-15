from django.db import migrations


PERMISSIONS = (
    ("manage.treasury.bank_accounts", "manage", "treasury.bank_accounts", "Gestionar cuentas bancarias"),
    ("manage.treasury.bank_movements", "manage", "treasury.bank_movements", "Registrar movimientos bancarios"),
    ("reconcile.treasury.bank", "reconcile", "treasury.bank", "Conciliar movimientos bancarios"),
)


def seed_permissions(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Role = apps.get_model("users", "Role")
    RolePermission = apps.get_model("users", "RolePermission")
    for code, action, module, description in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={"action_name": action, "module": module, "description": description},
        )
        for role in Role.objects.filter(name__in=("ADMIN", "SUPERUSER")):
            RolePermission.objects.get_or_create(role=role, permission=permission)


def unseed_permissions(apps, schema_editor):
    apps.get_model("users", "Permission").objects.filter(
        code__in=[item[0] for item in PERMISSIONS]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("treasury", "0003_bank_accounts_and_movements"),
        ("users", "0004_alter_permission_action_name"),
    ]
    operations = [migrations.RunPython(seed_permissions, unseed_permissions)]
