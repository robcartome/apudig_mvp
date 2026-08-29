from django.db import migrations


FIELD_NAMES = ("is_default_sale", "is_default_purchase")


def add_missing_product_unit_default_flags(apps, schema_editor):
    """Repair databases where the edited 0010 was recorded before these fields existed.

    Fresh databases already receive both columns from 0010, so this operation is a
    no-op there. Existing databases get only the physically missing columns.
    """
    ProductUnit = apps.get_model("inventory", "ProductUnit")
    table_name = ProductUnit._meta.db_table

    with schema_editor.connection.cursor() as cursor:
        existing_columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor, table_name
            )
        }

    for field_name in FIELD_NAMES:
        if field_name not in existing_columns:
            schema_editor.add_field(
                ProductUnit,
                ProductUnit._meta.get_field(field_name),
            )


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0013_productsupplier"),
    ]

    operations = [
        migrations.RunPython(
            add_missing_product_unit_default_flags,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
