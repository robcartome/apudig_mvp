from django.db import migrations


CODE = "create.pos.product"


def seed_permission(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Role = apps.get_model("users", "Role")
    RolePermission = apps.get_model("users", "RolePermission")
    permission, _ = Permission.objects.update_or_create(
        code=CODE,
        defaults={
            "action_name": "create",
            "module": "pos.product",
            "description": "Registrar productos desde el POS",
        },
    )
    for role in Role.objects.filter(name__in=("ADMIN", "SUPERUSER", "SELLER", "CASHIER")):
        RolePermission.objects.get_or_create(role=role, permission=permission)


def unseed_permission(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Permission.objects.filter(code=CODE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0012_cash_session_number_and_currency"),
        ("users", "0004_alter_permission_action_name"),
    ]

    operations = [migrations.RunPython(seed_permission, unseed_permission)]
