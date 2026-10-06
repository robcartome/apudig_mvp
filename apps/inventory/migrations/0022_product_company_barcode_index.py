from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0021_product_thumbnail_keys"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="product",
            index=models.Index(
                fields=("company", "barcode"),
                condition=~Q(barcode=""),
                name="idx_product_company_barcode",
            ),
        ),
    ]
