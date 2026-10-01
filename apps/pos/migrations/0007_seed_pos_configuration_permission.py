from django.db import migrations
from django.db.models import Q


def seed_permission(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Role = apps.get_model("users", "Role")
    RolePermission = apps.get_model("users", "RolePermission")
    permission, _ = Permission.objects.update_or_create(
        code="manage.pos.configuration",
        defaults={
            "action_name": "manage",
            "module": "pos.configuration",
            "description": "Configurar cajas del punto de venta",
        },
    )
    for role in Role.objects.filter(Q(name__iexact="ADMIN") | Q(name__iexact="SUPERUSER")):
        RolePermission.objects.get_or_create(role=role, permission=permission)


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0006_remove_cashtenderdeclaration_cash_tender_expected_gte_zero_and_more"),
        ("users", "0004_alter_permission_action_name"),
    ]

    operations = [migrations.RunPython(seed_permission, migrations.RunPython.noop)]
