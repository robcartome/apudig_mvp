from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0009_movement_origin_movement_reversal_of_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="product",
            old_name="image",
            new_name="image_key",
        ),
    ]
