from django.db import migrations, models


def classify_existing_means_of_payment(apps, schema_editor):
    MeansOfPayment = apps.get_model("sales", "MeansOfPayment")
    for means in MeansOfPayment.objects.all().iterator():
        name = means.name.casefold().strip()
        if name in {"efectivo", "cash"}:
            kind = "CASH"
        elif any(token in name for token in ("yape", "plin", "billetera")):
            kind = "DIGITAL_WALLET"
        elif any(token in name for token in ("tarjeta", "visa", "mastercard")):
            kind = "CARD"
        elif "transfer" in name:
            kind = "TRANSFER"
        else:
            continue
        MeansOfPayment.objects.filter(pk=means.pk).update(kind=kind)


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0013_remove_salesdocument_inventory_movement"),
    ]

    operations = [
        migrations.AddField(
            model_name="meansofpayment",
            name="kind",
            field=models.CharField(
                choices=[
                    ("CASH", "Efectivo"),
                    ("CARD", "Tarjeta"),
                    ("TRANSFER", "Transferencia"),
                    ("DIGITAL_WALLET", "Billetera digital"),
                    ("OTHER", "Otro"),
                ],
                default="OTHER",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="meansofpayment",
            name="requires_reference",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(
            classify_existing_means_of_payment,
            migrations.RunPython.noop,
        ),
    ]
