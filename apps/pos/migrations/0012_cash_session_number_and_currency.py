from django.db import migrations, models


def backfill_session_numbers(apps, schema_editor):
    PosRegister = apps.get_model("pos", "PosRegister")
    CashSession = apps.get_model("pos", "CashSession")
    for register in PosRegister.objects.all().iterator():
        number = 0
        for session in CashSession.objects.filter(register=register).order_by(
            "opened_at", "created_at", "pk"
        ).iterator():
            number += 1
            session.session_number = number
            currencies = set(
                session.sales_payments.values_list("currency", flat=True).distinct()
            )
            if not currencies:
                currencies = set(
                    session.transactions.values_list(
                        "sales_document__currency", flat=True
                    ).distinct()
                )
            if len(currencies) == 1:
                session.currency = currencies.pop()
            session.save(update_fields=("session_number", "currency"))
        register.current_session_number = number
        register.save(update_fields=("current_session_number",))


class Migration(migrations.Migration):
    dependencies = [("pos", "0011_salespayment_collection_fields")]

    operations = [
        migrations.AddField(
            model_name="posregister",
            name="current_session_number",
            field=models.PositiveBigIntegerField(default=0, editable=False),
        ),
        migrations.AddField(
            model_name="cashsession",
            name="currency",
            field=models.CharField(
                choices=[("PEN", "Soles"), ("USD", "Dolares")], default="PEN", max_length=3
            ),
        ),
        migrations.AddField(
            model_name="cashsession",
            name="session_number",
            field=models.PositiveBigIntegerField(default=0),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_session_numbers, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="cashsession",
            constraint=models.UniqueConstraint(
                fields=("register", "session_number"),
                name="uniq_cash_session_number_per_register",
            ),
        ),
    ]
