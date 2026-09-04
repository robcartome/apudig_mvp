import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0016_movement_purchase_receipt"),
        ("purchases", "0008_purchasedocument_payment_method"),
    ]

    operations = [
        migrations.AlterField(
            model_name="purchasedocument",
            name="register_inventory_movement",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="PurchaseDocumentReceiptMatch",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("stock_quantity", models.DecimalField(decimal_places=6, max_digits=18)),
                ("movement_detail", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="purchase_receipt_matches", to="inventory.movementdetail")),
                ("purchase_document_line", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="receipt_matches", to="purchases.purchasedocumentline")),
            ],
            options={"db_table": "purchase_document_receipt_matches"},
        ),
        migrations.AddConstraint(
            model_name="purchasedocumentreceiptmatch",
            constraint=models.UniqueConstraint(fields=("purchase_document_line", "movement_detail"), name="uniq_purchase_document_receipt_match"),
        ),
        migrations.AddConstraint(
            model_name="purchasedocumentreceiptmatch",
            constraint=models.CheckConstraint(condition=models.Q(("stock_quantity__gt", 0)), name="purchase_document_receipt_match_quantity_gt_zero"),
        ),
    ]
