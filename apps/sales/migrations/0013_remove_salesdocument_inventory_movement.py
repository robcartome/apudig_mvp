from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0019_movement_sales_document"),
        ("sales", "0012_sales_document_issue_datetime_and_legacy_relation"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="salesdocument",
            name="inventory_movement",
        ),
    ]
