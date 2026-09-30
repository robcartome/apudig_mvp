from django.db import migrations


ROLE_CODES = {
    "SELLER": ("change.pos.price",),
    "CASHIER": ("change.pos.price", "apply.pos.discount"),
}


def grant_permissions(apps, schema_editor):
    Role = apps.get_model("users", "Role")
    Permission = apps.get_model("users", "Permission")
    RolePermission = apps.get_model("users", "RolePermission")
    for role_name, codes in ROLE_CODES.items():
        role = Role.objects.filter(name__iexact=role_name).first()
        if role is None:
            continue
        for permission in Permission.objects.filter(code__in=codes):
            RolePermission.objects.get_or_create(role=role, permission=permission)


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0007_seed_pos_configuration_permission"),
        ("users", "0004_alter_permission_action_name"),
    ]

    operations = [migrations.RunPython(grant_permissions, migrations.RunPython.noop)]
