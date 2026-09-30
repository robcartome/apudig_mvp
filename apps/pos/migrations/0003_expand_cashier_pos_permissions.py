from django.db import migrations


CASHIER_PERMISSION_CODES = (
    "close.pos.cash",
    "manage.pos.cash_movements",
    "consolidate.pos.invoice",
)


def grant_cashier_permissions(apps, schema_editor):
    Role = apps.get_model("users", "Role")
    Permission = apps.get_model("users", "Permission")
    RolePermission = apps.get_model("users", "RolePermission")
    cashier = Role.objects.filter(name__iexact="CASHIER").first()
    if cashier is None:
        return
    for permission in Permission.objects.filter(code__in=CASHIER_PERMISSION_CODES):
        RolePermission.objects.get_or_create(role=cashier, permission=permission)


def revoke_cashier_permissions(apps, schema_editor):
    RolePermission = apps.get_model("users", "RolePermission")
    RolePermission.objects.filter(
        role__name__iexact="CASHIER",
        permission__code__in=CASHIER_PERMISSION_CODES,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0002_seed_pos_permissions"),
    ]

    operations = [
        migrations.RunPython(grant_cashier_permissions, revoke_cashier_permissions),
    ]
