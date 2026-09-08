from django.db import migrations, models
from django.utils import timezone


def assign_annual_operation_sequences(apps, schema_editor):
    Movement = apps.get_model("inventory", "Movement")
    database = schema_editor.connection.alias
    manager = Movement._base_manager.using(database)

    counters = {}
    movements = list(manager.order_by("store_id", "date", "created_at", "pk"))
    for movement in movements:
        operation_date = movement.date
        if timezone.is_aware(operation_date):
            operation_date = timezone.localtime(operation_date)
        operation_year = operation_date.year
        key = (movement.store_id, operation_year)
        counters[key] = counters.get(key, 0) + 1
        movement.operation_year = operation_year
        movement.operation_number = counters[key]

    if movements:
        manager.bulk_update(
            movements,
            ("operation_year", "operation_number"),
            batch_size=500,
        )


def restore_store_operation_sequences(apps, schema_editor):
    """Avoid collisions if this migration is rolled back across several years."""
    Movement = apps.get_model("inventory", "Movement")
    database = schema_editor.connection.alias
    manager = Movement._base_manager.using(database)

    counters = {}
    movements = list(manager.order_by("store_id", "date", "created_at", "pk"))
    for movement in movements:
        key = movement.store_id
        counters[key] = counters.get(key, 0) + 1
        movement.operation_number = counters[key]

    if movements:
        manager.bulk_update(movements, ("operation_number",), batch_size=500)


class Migration(migrations.Migration):

    # Commit the data update before PostgreSQL creates the new constraint.
    atomic = False

    dependencies = [
        ("inventory", "0017_movement_operation_number_and_state_flow"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="movement",
            name="uniq_store_movement_operation_number",
        ),
        migrations.AddField(
            model_name="movement",
            name="operation_year",
            field=models.PositiveSmallIntegerField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(assign_annual_operation_sequences, restore_store_operation_sequences),
        migrations.AlterField(
            model_name="movement",
            name="operation_year",
            field=models.PositiveSmallIntegerField(editable=False),
        ),
        migrations.AddConstraint(
            model_name="movement",
            constraint=models.UniqueConstraint(
                fields=("store", "operation_year", "operation_number"),
                name="uniq_store_year_movement_operation_number",
            ),
        ),
    ]
