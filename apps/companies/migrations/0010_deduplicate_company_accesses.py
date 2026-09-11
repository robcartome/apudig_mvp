from django.db import migrations, models
from django.db.models import Count


def deduplicate_company_accesses(apps, schema_editor):
    UserCompanyAccess = apps.get_model("companies", "UserCompanyAccess")

    duplicated_groups = (
        UserCompanyAccess.objects.filter(store__isnull=True)
        .values("user_id", "company_id")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )

    for group in duplicated_groups.iterator():
        accesses = UserCompanyAccess.objects.filter(
            user_id=group["user_id"],
            company_id=group["company_id"],
            store__isnull=True,
        ).order_by("-is_default", "created_at", "id")
        access_to_keep = accesses.first()
        accesses.exclude(pk=access_to_keep.pk).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0009_companyoperationalsettings_inventory_allow_negative_stock"),
    ]

    operations = [
        migrations.RunPython(
            deduplicate_company_accesses,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="usercompanyaccess",
            constraint=models.UniqueConstraint(
                fields=("user", "company"),
                condition=models.Q(store__isnull=True),
                name="uniq_user_company_without_store",
            ),
        ),
    ]
