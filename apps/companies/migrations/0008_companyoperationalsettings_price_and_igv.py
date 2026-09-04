from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0007_companyoperationalsettings"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyoperationalsettings",
            name="price_decimal_places",
            field=models.PositiveSmallIntegerField(default=2),
        ),
        migrations.AddField(
            model_name="companyoperationalsettings",
            name="default_igv_rate",
            field=models.DecimalField(decimal_places=2, default=Decimal("18"), max_digits=5),
        ),
    ]
