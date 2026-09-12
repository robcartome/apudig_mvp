from django.db.models import Q

from apps.users.models import UserRole, UserStore

from .models import Company, Store, UserCompanyAccess


def get_active_companies():
    return Company.objects.filter(is_active=True).order_by("name")


def get_stores_for_company(company_id: str):
    return Store.objects.for_company(company_id).filter(active=True).order_by("name")


def get_user_selectable_accesses(user):
    """Return only active company/store contexts authorized for ``user``.

    ``UserCompanyAccess`` supplies the stable option id used by the forms, while
    ``UserRole`` and ``UserStore`` are the authorization sources.
    """
    if not user or not user.is_authenticated:
        return UserCompanyAccess.objects.none()

    accesses = UserCompanyAccess.objects.filter(
        user=user,
        company__is_active=True,
    ).filter(
        Q(store__isnull=True) | Q(store__active=True),
    )

    if not user.is_superuser:
        administered_company_ids = UserRole.objects.filter(
            user=user,
            role__name__iexact="ADMIN",
        ).values_list("company_id", flat=True)
        assigned_store_ids = UserStore.objects.filter(
            user=user,
            is_active=True,
            store__active=True,
            store__company__is_active=True,
        ).values_list("store_id", flat=True)
        companies_without_active_stores = Company.objects.filter(
            is_active=True,
        ).exclude(
            stores__active=True,
        ).values_list("pk", flat=True)

        accesses = accesses.filter(
            Q(company_id__in=administered_company_ids)
            | Q(store_id__in=assigned_store_ids)
            | Q(
                store__isnull=True,
                company_id__in=companies_without_active_stores,
            )
        )

    return (
        accesses.select_related("company", "store")
        .selectable()
        .order_by("-is_default", "company__name", "store__name")
    )
