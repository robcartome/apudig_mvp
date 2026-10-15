from django.db import migrations


PERMISSIONS = (
    ("read.treasury", "read", "treasury", "Acceder al módulo de Tesorería"),
    (
        "manage.treasury.cash_safe", "manage", "treasury.cash_safe",
        "Gestionar movimientos de caja fuerte",
    ),
    (
        "authorize.treasury.cash_safe", "authorize", "treasury.cash_safe",
        "Autorizar salidas y ajustes de caja fuerte",
    ),
)


def seed_permissions(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Role = apps.get_model("users", "Role")
    RolePermission = apps.get_model("users", "RolePermission")
    for code, action, module, description in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "action_name": action,
                "module": module,
                "description": description,
            },
        )
        for role in Role.objects.filter(name__in=("ADMIN", "SUPERUSER")):
            RolePermission.objects.get_or_create(role=role, permission=permission)


def unseed_permissions(apps, schema_editor):
    apps.get_model("users", "Permission").objects.filter(
        code__in=[item[0] for item in PERMISSIONS]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0004_alter_permission_action_name"),
        ("pos", "0015_cashmovement_payment_details"),
    ]

    operations = [migrations.RunPython(seed_permissions, unseed_permissions)]
