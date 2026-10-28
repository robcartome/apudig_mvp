from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("partners", "0004_documenttype_commercial_fields"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="customer",
            unique_together=set(),
        ),
        migrations.AlterField(
            model_name="customer",
            name="document_type",
            field=models.CharField(
                choices=[
                    ("0", "Sin documento"),
                    ("1", "DNI"),
                    ("4", "Carné de extranjería"),
                    ("6", "RUC"),
                    ("7", "Pasaporte"),
                    ("A", "Cédula diplomática"),
                ],
                max_length=2,
            ),
        ),
        migrations.AlterField(
            model_name="customer",
            name="document_number",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.UniqueConstraint(
                condition=~models.Q(document_number=""),
                fields=("company", "document_type", "document_number"),
                name="uniq_customer_company_document",
            ),
        ),
    ]
