from django.db import migrations, models


def initialize_payment_method_options(apps, schema_editor):
    PaymentMethod = apps.get_model("sales", "PaymentMethod")
    for method in PaymentMethod.objects.all().iterator():
        method.receives_change = method.is_cash
        method.immediate_payment = method.is_cash
        method.is_credit = not method.is_cash
        method.save(update_fields=("receives_change", "immediate_payment", "is_credit"))


class Migration(migrations.Migration):
    dependencies = [("sales", "0015_salesdocument_due_date")]

    operations = [
        migrations.AddField(
            model_name="paymentmethod",
            name="allows_advance",
            field=models.BooleanField(default=False, verbose_name="Permite pago adelantado"),
        ),
        migrations.AddField(
            model_name="paymentmethod",
            name="credit_days",
            field=models.PositiveIntegerField(default=0, verbose_name="Días de crédito"),
        ),
        migrations.AddField(
            model_name="paymentmethod",
            name="immediate_payment",
            field=models.BooleanField(default=True, verbose_name="Pago inmediato"),
        ),
        migrations.AddField(
            model_name="paymentmethod",
            name="is_credit",
            field=models.BooleanField(default=False, verbose_name="Es crédito"),
        ),
        migrations.AddField(
            model_name="paymentmethod",
            name="receives_change",
            field=models.BooleanField(
                default=False,
                help_text="Permite registrar un importe recibido mayor y calcular vuelto.",
                verbose_name="Recibe vuelto",
            ),
        ),
        migrations.RunPython(initialize_payment_method_options, migrations.RunPython.noop),
    ]
