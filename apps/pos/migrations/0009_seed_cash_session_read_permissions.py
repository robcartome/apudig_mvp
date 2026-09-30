from django.db import migrations


PERMISSIONS = (
    ("read", "pos.cash_sessions", "Consultar sesiones de caja propias"),
    ("read", "pos.cash_sessions_all", "Auditar todas las sesiones de caja"),
)


def seed_permissions(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Role = apps.get_model("users", "Role")
    RolePermission = apps.get_model("users", "RolePermission")
    permissions = {}
    for action, module, description in PERMISSIONS:
        code = f"{action}.{module}"
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={"action_name": action, "module": module, "description": description},
        )
        permissions[code] = permission

    for role in Role.objects.all():
        role_name = role.name.upper()
        codes = set()
        if role_name in {"ADMIN", "SUPERUSER"}:
            codes = set(permissions)
        elif role_name == "CASHIER":
            codes = {"read.pos.cash_sessions"}
        for code in codes:
            RolePermission.objects.get_or_create(role=role, permission=permissions[code])


def unseed_permissions(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Permission.objects.filter(code__in=(
        "read.pos.cash_sessions", "read.pos.cash_sessions_all",
    )).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0008_grant_pos_line_edit_permissions"),
        ("users", "0004_alter_permission_action_name"),
    ]

    operations = [migrations.RunPython(seed_permissions, unseed_permissions)]
