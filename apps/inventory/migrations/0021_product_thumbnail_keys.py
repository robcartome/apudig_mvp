from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0020_pricing_tax_and_cost_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="image_thumbnail_key",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="product",
            name="secondary_image_thumbnail_key",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="product",
            name="tertiary_image_thumbnail_key",
            field=models.CharField(blank=True, max_length=500),
        ),
    ]
