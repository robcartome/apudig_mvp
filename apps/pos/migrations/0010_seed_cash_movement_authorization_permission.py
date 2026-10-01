from django.db import migrations


CODE = "authorize.pos.cash_movement"


def seed_permission(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Role = apps.get_model("users", "Role")
    RolePermission = apps.get_model("users", "RolePermission")
    permission, _ = Permission.objects.update_or_create(
        code=CODE,
        defaults={
            "action_name": "authorize",
            "module": "pos.cash_movement",
            "description": "Autorizar retiros y depositos de caja",
        },
    )
    for role in Role.objects.filter(name__iexact="ADMIN"):
        RolePermission.objects.get_or_create(role=role, permission=permission)


def unseed_permission(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Permission.objects.filter(code=CODE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0009_seed_cash_session_read_permissions"),
        ("users", "0004_alter_permission_action_name"),
    ]

    operations = [migrations.RunPython(seed_permission, unseed_permission)]
