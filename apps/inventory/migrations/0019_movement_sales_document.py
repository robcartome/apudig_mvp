from django.db import migrations, models
import django.db.models.deletion


def copy_sales_movement_relations(apps, schema_editor):
    Movement = apps.get_model("inventory", "Movement")
    SalesDocument = apps.get_model("sales", "SalesDocument")

    for document in SalesDocument.objects.exclude(inventory_movement_id=None).iterator():
        Movement.objects.filter(pk=document.inventory_movement_id).update(
            sales_document_id=document.pk
        )

    for movement in Movement.objects.filter(
        sales_document_id=None,
        reversal_of__sales_document_id__isnull=False,
    ).select_related("reversal_of").iterator():
        movement.sales_document_id = movement.reversal_of.sales_document_id
        movement.save(update_fields=["sales_document"])


def clear_sales_movement_relations(apps, schema_editor):
    apps.get_model("inventory", "Movement").objects.update(sales_document_id=None)


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0018_movement_annual_operation_sequence"),
        ("sales", "0012_sales_document_issue_datetime_and_legacy_relation"),
    ]

    operations = [
        migrations.AddField(
            model_name="movement",
            name="sales_document",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="inventory_movements",
                to="sales.salesdocument",
            ),
        ),
        migrations.RunPython(copy_sales_movement_relations, clear_sales_movement_relations),
    ]
