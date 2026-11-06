from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("companies", "0014_companyoperationalsettings_purchase_due_notification_days"),
    ]

    operations = [
        migrations.AddField(
            model_name="companybranding",
            name="show_company_name_with_logo",
            field=models.BooleanField(
                default=False,
                verbose_name="Mostrar razón social junto al logo",
            ),
        ),
    ]
