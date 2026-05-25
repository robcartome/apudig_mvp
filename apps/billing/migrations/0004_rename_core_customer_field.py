"""
Rename BillingInvoice.core_customer field → customer,
following the partners app rename of CoreCustomer → Customer.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0003_initial"),
        ("partners", "0003_rename_corecustomer_to_customer"),
    ]

    operations = [
        migrations.RenameField(
            model_name="billinginvoice",
            old_name="core_customer",
            new_name="customer",
        ),
    ]
