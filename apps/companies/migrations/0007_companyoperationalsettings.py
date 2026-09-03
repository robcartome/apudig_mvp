import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0006_company_address_company_email_company_phone_and_more"),
        ("partners", "0004_documenttype_commercial_fields"),
        ("sales", "0010_sale_lines_uom"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyOperationalSettings",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("inventory_quantity_editable", models.BooleanField(default=True)),
                ("inventory_unit_cost_editable", models.BooleanField(default=True)),
                ("sales_value_unit_editable", models.BooleanField(default=False)),
                ("sales_price_unit_editable", models.BooleanField(default=True)),
                ("sales_total_editable", models.BooleanField(default=False)),
                ("purchases_value_unit_editable", models.BooleanField(default=True)),
                ("purchases_price_unit_editable", models.BooleanField(default=True)),
                ("purchases_total_editable", models.BooleanField(default=False)),
                ("company", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="operational_settings", to="companies.company")),
                ("default_customer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="default_for_company_settings", to="partners.customer")),
                ("default_purchase_document_type", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="default_purchase_for_companies", to="partners.documenttype")),
                ("default_purchase_payment_method", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="default_purchases_for_companies", to="sales.paymentmethod")),
                ("default_sales_document_type", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="default_sales_for_companies", to="partners.documenttype")),
                ("default_sales_payment_method", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="default_sales_for_companies", to="sales.paymentmethod")),
                ("default_supplier", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="default_for_company_settings", to="partners.supplier")),
            ],
            options={"db_table": "company_operational_settings"},
        ),
    ]
