from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0018_meansofpayment_bank_account"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesquotation",
            name="seller_name",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="salesquotationline",
            name="is_manual",
            field=models.BooleanField(default=False),
        ),
    ]
