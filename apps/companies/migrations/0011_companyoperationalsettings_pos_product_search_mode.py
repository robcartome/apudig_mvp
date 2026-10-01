from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("companies", "0010_deduplicate_company_accesses"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyoperationalsettings",
            name="pos_product_search_mode",
            field=models.CharField(
                choices=[
                    ("SEARCH", "Buscador rápido"),
                    ("CATALOG", "Catálogo visual por tarjetas"),
                ],
                default="SEARCH",
                max_length=10,
            ),
        ),
    ]
