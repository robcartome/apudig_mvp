from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0008_unique_quotation_series_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesdocumentline",
            name="memo",
            field=models.CharField(blank=True, max_length=500),
        ),
    ]
