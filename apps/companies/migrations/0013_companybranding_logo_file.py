from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("companies", "0012_taxrate"),
    ]

    operations = [
        migrations.AddField(
            model_name="companybranding",
            name="logo_file",
            field=models.ImageField(blank=True, upload_to="company_logos/%Y/%m/"),
        ),
    ]
