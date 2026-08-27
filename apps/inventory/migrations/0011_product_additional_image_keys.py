from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0010_rename_product_image_to_image_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="secondary_image_key",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="product",
            name="tertiary_image_key",
            field=models.CharField(blank=True, max_length=500),
        ),
    ]
