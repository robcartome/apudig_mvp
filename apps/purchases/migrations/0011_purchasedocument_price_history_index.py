from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0010_purchase_document_global_discount"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="purchasedocument",
            index=models.Index(
                fields=["company", "store", "document_status", "issue_date", "created_at"],
                name="purch_doc_price_scope_idx",
            ),
        ),
    ]
