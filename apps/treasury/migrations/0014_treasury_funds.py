import uuid

import django.db.models.deletion
from django.db import migrations, models


def create_default_funds(apps, schema_editor):
    Store = apps.get_model("companies", "Store")
    TreasuryFund = apps.get_model("treasury", "TreasuryFund")
    CashSafeMovement = apps.get_model("treasury", "CashSafeMovement")
    CashSafeCount = apps.get_model("treasury", "CashSafeCount")
    for store in Store.objects.all().iterator():
        fund = TreasuryFund.objects.create(
            company_id=store.company_id,
            store_id=store.pk,
            code="PRINCIPAL",
            name="Caja fuerte principal",
            fund_type="SAFE",
            is_default=True,
            active=True,
        )
        CashSafeMovement.objects.filter(store_id=store.pk).update(fund_id=fund.pk)
        CashSafeCount.objects.filter(store_id=store.pk).update(fund_id=fund.pk)


class Migration(migrations.Migration):
    dependencies = [
        ("companies", "0012_taxrate"),
        ("treasury", "0013_cash_safe_document_traceability"),
    ]

    operations = [
        migrations.CreateModel(
            name="TreasuryFund",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("code", models.CharField(max_length=30)),
                ("name", models.CharField(max_length=150)),
                ("fund_type", models.CharField(choices=[("SAFE", "Caja fuerte"), ("PETTY_CASH", "Caja chica"), ("ADMINISTRATIVE", "Fondo administrativo"), ("OTHER", "Otro fondo")], default="SAFE", max_length=20)),
                ("is_default", models.BooleanField(default=False)),
                ("active", models.BooleanField(default=True)),
                ("notes", models.CharField(blank=True, max_length=300)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="treasury_funds", to="companies.company")),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="treasury_funds", to="companies.store")),
            ],
            options={"db_table": "treasury_funds", "ordering": ("store__name", "name")},
        ),
        migrations.AddConstraint(
            model_name="treasuryfund",
            constraint=models.UniqueConstraint(fields=("store", "code"), name="uniq_treasury_fund_store_code"),
        ),
        migrations.AddConstraint(
            model_name="treasuryfund",
            constraint=models.UniqueConstraint(condition=models.Q(("is_default", True)), fields=("store",), name="uniq_treasury_default_fund_per_store"),
        ),
        migrations.AddField(
            model_name="cashsafemovement",
            name="fund",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="cash_movements", to="treasury.treasuryfund"),
        ),
        migrations.AddField(
            model_name="cashsafecount",
            name="fund",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="cash_counts", to="treasury.treasuryfund"),
        ),
        migrations.RunPython(create_default_funds, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="cashsafemovement",
            name="fund",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cash_movements", to="treasury.treasuryfund"),
        ),
        migrations.AlterField(
            model_name="cashsafecount",
            name="fund",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cash_counts", to="treasury.treasuryfund"),
        ),
    ]
