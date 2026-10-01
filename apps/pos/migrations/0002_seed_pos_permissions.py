from django.db import migrations


PERMISSIONS = (
    ("read", "pos", "Acceder al punto de venta"),
    ("sell", "pos", "Registrar ventas en el punto de venta"),
    ("open", "pos.cash", "Abrir sesiones de caja"),
    ("close", "pos.cash", "Cerrar sesiones de caja"),
    ("manage", "pos.cash_movements", "Registrar ingresos y retiros de caja"),
    ("authorize", "pos.cash_difference", "Autorizar diferencias de caja"),
    ("change", "pos.pricelist", "Cambiar la lista de precios del POS"),
    ("change", "pos.price", "Modificar precios en el POS"),
    ("apply", "pos.discount", "Aplicar descuentos en el POS"),
    ("authorize", "pos.discount", "Autorizar descuentos especiales"),
    ("create", "pos.customer", "Registrar clientes desde el POS"),
    ("issue", "pos.invoice", "Emitir comprobantes desde el POS"),
    ("consolidate", "pos.invoice", "Consolidar Notas de Venta en una factura"),
    ("void", "pos.sale", "Anular ventas POS"),
    ("refund", "pos.sale", "Registrar devoluciones POS"),
    ("reprint", "pos.receipt", "Reimprimir tickets POS"),
)

ROLE_CODES = {
    "SELLER": {
        "read.pos", "sell.pos", "change.pos.pricelist", "apply.pos.discount",
        "create.pos.customer", "issue.pos.invoice", "reprint.pos.receipt",
    },
    "CASHIER": {
        "read.pos", "sell.pos", "open.pos.cash", "close.pos.cash",
        "manage.pos.cash_movements", "create.pos.customer", "issue.pos.invoice",
        "consolidate.pos.invoice", "reprint.pos.receipt",
    },
}


def seed_pos_permissions(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Role = apps.get_model("users", "Role")
    RolePermission = apps.get_model("users", "RolePermission")

    permission_by_code = {}
    for action, module, description in PERMISSIONS:
        code = f"{action}.{module}"
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "action_name": action,
                "module": module,
                "description": description,
            },
        )
        permission_by_code[code] = permission

    all_codes = set(permission_by_code)
    for role in Role.objects.all():
        role_name = role.name.upper()
        if role_name in {"ADMIN", "SUPERUSER"}:
            codes = all_codes
        else:
            codes = ROLE_CODES.get(role_name, set())
        for code in codes:
            RolePermission.objects.get_or_create(
                role=role,
                permission=permission_by_code[code],
            )


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0001_initial"),
        ("users", "0004_alter_permission_action_name"),
    ]

    operations = [
        migrations.RunPython(seed_pos_permissions, migrations.RunPython.noop),
    ]
