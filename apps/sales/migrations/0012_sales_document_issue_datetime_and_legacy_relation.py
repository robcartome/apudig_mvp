from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0018_movement_annual_operation_sequence"),
        ("sales", "0011_sales_document_global_discount"),
    ]

    operations = [
        migrations.AlterField(
            model_name="salesdocument",
            name="issue_date",
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name="salesdocument",
            name="inventory_movement",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="legacy_sales_document",
                to="inventory.movement",
            ),
        ),
    ]
