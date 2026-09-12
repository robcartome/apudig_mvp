from django.db import migrations, models


ROLE_PRIORITY = ("ADMIN", "SELLER", "CASHIER", "WAREHOUSE")


def backfill_scoped_store_access(apps, schema_editor):
    User = apps.get_model("users", "User")
    UserRole = apps.get_model("users", "UserRole")
    UserStore = apps.get_model("users", "UserStore")
    Store = apps.get_model("companies", "Store")
    UserCompanyAccess = apps.get_model("companies", "UserCompanyAccess")

    role_names = {}
    for role_name in ROLE_PRIORITY:
        assignments = UserRole.objects.filter(
            role__name__iexact=role_name,
        ).values_list("user_id", "company_id")
        for user_id, company_id in assignments.iterator():
            role_names.setdefault((str(user_id), str(company_id)), role_name)

    company_admin_pairs = UserRole.objects.filter(
        role__name__iexact="ADMIN",
    ).values_list("user_id", "company_id")
    for user_id, company_id in company_admin_pairs.iterator():
        UserCompanyAccess.objects.get_or_create(
            user_id=user_id,
            company_id=company_id,
            store_id=None,
            defaults={"is_default": False},
        )
        for store in Store.objects.filter(company_id=company_id, active=True).iterator():
            UserCompanyAccess.objects.get_or_create(
                user_id=user_id,
                company_id=company_id,
                store_id=store.pk,
                defaults={"is_default": False},
            )
            UserStore.objects.update_or_create(
                user_id=user_id,
                store_id=store.pk,
                defaults={"role": "ADMIN", "is_active": True},
            )

    store_accesses = UserCompanyAccess.objects.filter(
        store__isnull=False,
    ).values_list("user_id", "company_id", "store_id")
    for user_id, company_id, store_id in store_accesses.iterator():
        role = role_names.get((str(user_id), str(company_id)), "SELLER")
        UserStore.objects.get_or_create(
            user_id=user_id,
            store_id=store_id,
            defaults={"role": role, "is_active": True},
        )

    for user_id in User.objects.filter(is_superuser=True, is_active=True).values_list(
        "pk", flat=True
    ).iterator():
        for store in Store.objects.filter(active=True).iterator():
            UserStore.objects.update_or_create(
                user_id=user_id,
                store_id=store.pk,
                defaults={"role": "ADMIN", "is_active": True},
            )


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0010_deduplicate_company_accesses"),
        ("users", "0002_alter_permission_options_alter_role_options_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userstore",
            name="role",
            field=models.CharField(
                choices=[
                    ("ADMIN", "Admin"),
                    ("SELLER", "Vendedor"),
                    ("CASHIER", "Cajero"),
                    ("WAREHOUSE", "Almacenero"),
                ],
                default="SELLER",
                max_length=50,
            ),
        ),
        migrations.RunPython(
            backfill_scoped_store_access,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
