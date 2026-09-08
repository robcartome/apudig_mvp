from django.db import migrations, models


def migrate_existing_movements(apps, schema_editor):
    Movement = apps.get_model("inventory", "Movement")
    database = schema_editor.connection.alias
    manager = Movement._base_manager.using(database)

    counters = {}
    movements = list(manager.order_by("store_id", "date", "created_at", "pk"))
    for movement in movements:
        key = movement.store_id
        counters[key] = counters.get(key, 0) + 1
        movement.operation_number = counters[key]

        # Historical drafts and closed rows already affected StockByWarehouse.
        # Reclassify them as applied without touching stock a second time.
        if movement.status in ("DRAFT", "CLOSED"):
            movement.status = "CONFIRMED"
            if movement.confirmed_at is None:
                movement.confirmed_at = movement.created_at
            if movement.confirmed_by_id is None:
                movement.confirmed_by_id = movement.created_by_id

    if movements:
        manager.bulk_update(
            movements,
            ("operation_number", "status", "confirmed_at", "confirmed_by"),
            batch_size=500,
        )


class Migration(migrations.Migration):

    # PostgreSQL cannot add the unique constraint in the same transaction that
    # bulk-updates movements because deferred FK triggers are still pending.
    # Let each operation commit before the following schema change.
    atomic = False

    dependencies = [
        ("inventory", "0016_movement_purchase_receipt"),
    ]

    operations = [
        migrations.AddField(
            model_name="movement",
            name="operation_number",
            field=models.PositiveBigIntegerField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(migrate_existing_movements, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="movement",
            constraint=models.UniqueConstraint(
                fields=("store", "operation_number"),
                name="uniq_store_movement_operation_number",
            ),
        ),
        migrations.AlterField(
            model_name="movement",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Borrador"),
                    ("CONFIRMED", "Aplicado"),
                    ("REVERSED", "Revertido"),
                ],
                default="DRAFT",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="movementauditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("CREATE", "Creación"),
                    ("UPDATE", "Actualización"),
                    ("CONFIRM", "Confirmación"),
                    ("CLOSE", "Cierre legado"),
                    ("REVERSE", "Reversión"),
                    ("DELETE", "Eliminación"),
                ],
                max_length=20,
            ),
        ),
    ]
