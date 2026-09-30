from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0014_meansofpayment_kind_and_reference"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesdocument",
            name="due_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
