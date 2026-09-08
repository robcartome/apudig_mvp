from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0008_companyoperationalsettings_price_and_igv"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyoperationalsettings",
            name="inventory_allow_negative_stock",
            field=models.BooleanField(default=False),
        ),
    ]
