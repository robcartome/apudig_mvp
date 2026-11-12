from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("websites", "0005_websitecatalogsettings_websiteproduct")]

    operations = [
        migrations.AddField(
            model_name="website",
            name="template_key",
            field=models.CharField(default="ecommerce", max_length=64),
        ),
        migrations.AddField(
            model_name="website",
            name="template_schema_version",
            field=models.PositiveSmallIntegerField(default=1),
        ),
    ]
