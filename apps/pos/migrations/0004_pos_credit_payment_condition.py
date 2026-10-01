from django.db import migrations, models


PERMISSION_CODE = "sell.pos.credit"


def seed_credit_permission(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Role = apps.get_model("users", "Role")
    RolePermission = apps.get_model("users", "RolePermission")

    permission, _ = Permission.objects.update_or_create(
        code=PERMISSION_CODE,
        defaults={
            "action_name": "sell",
            "module": "pos.credit",
            "description": "Registrar ventas a credito en el punto de venta",
        },
    )
    for role_name in ("ADMIN", "SUPERUSER"):
        for role in Role.objects.filter(name__iexact=role_name):
            RolePermission.objects.get_or_create(role=role, permission=permission)


def remove_credit_permission(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Permission.objects.filter(code=PERMISSION_CODE).delete()


def backfill_payment_status(apps, schema_editor):
    PosTransaction = apps.get_model("pos", "PosTransaction")
    SalesPayment = apps.get_model("pos", "SalesPayment")
    for transaction in PosTransaction.objects.select_related("sales_document").iterator():
        paid = (
            SalesPayment.objects.filter(
                sales_document_id=transaction.sales_document_id,
                status="REGISTERED",
            ).aggregate(total=models.Sum("amount_in_sale_currency"))["total"]
            or 0
        )
        if paid >= transaction.sales_document.total:
            payment_status = "PAID"
        elif paid > 0:
            payment_status = "PARTIAL"
        else:
            payment_status = "PENDING"
        PosTransaction.objects.filter(pk=transaction.pk).update(
            payment_status=payment_status
        )


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0003_expand_cashier_pos_permissions"),
        ("sales", "0015_salesdocument_due_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="postransaction",
            name="payment_condition",
            field=models.CharField(
                choices=[("CASH", "Contado"), ("CREDIT", "Credito")],
                default="CASH",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="postransaction",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pendiente"),
                    ("PARTIAL", "Pago parcial"),
                    ("PAID", "Pagado"),
                ],
                default="PENDING",
                max_length=10,
            ),
        ),
        migrations.RunPython(backfill_payment_status, migrations.RunPython.noop),
        migrations.RunPython(seed_credit_permission, remove_credit_permission),
    ]
