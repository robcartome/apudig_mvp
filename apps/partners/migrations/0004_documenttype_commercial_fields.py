from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("partners", "0003_rename_corecustomer_to_customer")]

    operations = [
        migrations.AlterField(
            model_name="documenttype",
            name="code",
            field=models.CharField(max_length=10, unique=True),
        ),
        migrations.AlterField(
            model_name="documenttype",
            name="abbreviation",
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(model_name="documenttype", name="category", field=models.CharField(default="INTERNAL", max_length=20)),
        migrations.AddField(model_name="documenttype", name="is_sunat", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="documenttype", name="sunat_code", field=models.CharField(blank=True, max_length=4)),
        migrations.AddField(model_name="documenttype", name="affects_stock", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="documenttype", name="affects_accounting", field=models.BooleanField(default=False)),
        migrations.AlterField(model_name="documenttype", name="category", field=models.CharField(choices=[("SALES", "Ventas"), ("BILLING", "Facturación"), ("LOGISTICS", "Logística"), ("INTERNAL", "Interno")], max_length=20)),
    ]
