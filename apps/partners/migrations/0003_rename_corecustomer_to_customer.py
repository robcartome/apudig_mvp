"""
Rename CoreCustomer → Customer (class + table + related field on SalesCustomerProfile).
Safe to run on pre-production databases.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("partners", "0002_company_scoped_partners"),
        # These migrations still reference partners.corecustomer (historical);
        # they must all be applied BEFORE the rename so Django's state is consistent.
        ("billing", "0002_initial"),
        ("inventory", "0003_initial"),
        ("sales", "0002_initial"),
    ]

    operations = [
        # 1. Rename the model in Django's migration graph (also updates FK references
        #    in other apps that point to 'partners.CoreCustomer').
        migrations.RenameModel(
            old_name="CoreCustomer",
            new_name="Customer",
        ),
        # 2. Rename the physical table from core_customers → customers.
        migrations.AlterModelTable(
            name="customer",
            table="customers",
        ),
        # 3. Rename the OneToOneField on SalesCustomerProfile.
        migrations.RenameField(
            model_name="salescustomerprofile",
            old_name="core_customer",
            new_name="customer",
        ),
    ]
