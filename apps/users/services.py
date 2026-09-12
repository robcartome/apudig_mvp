"""
users/services.py — Lógica de negocio de usuarios, roles y permisos.
"""
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.companies.models import Store, UserCompanyAccess

from .models import UserStore

User = get_user_model()


def get_user_roles_for_company(user, company_id: str):
    """Devuelve los roles asignados a un usuario en una empresa específica."""
    return (
        user.user_roles
        .select_related("role")
        .filter(company_id=company_id)
    )


def get_user_stores(user):
    """Devuelve las sucursales a las que tiene acceso el usuario."""
    return (
        user.user_stores
        .select_related("store", "store__company")
        .filter(is_active=True)
    )


@transaction.atomic
def grant_company_admin_access(user, company) -> None:
    """Grant a company administrator access to every active branch."""
    UserCompanyAccess.objects.get_or_create(
        user=user,
        company=company,
        store=None,
        defaults={"is_default": False},
    )
    for store in Store.objects.filter(company=company, active=True):
        UserCompanyAccess.objects.get_or_create(
            user=user,
            company=company,
            store=store,
            defaults={"is_default": False},
        )
        UserStore.objects.update_or_create(
            user=user,
            store=store,
            defaults={"role": "ADMIN", "is_active": True},
        )


@transaction.atomic
def revoke_company_admin_access(user, company) -> None:
    """Revoke auto-granted branch access after removing the company ADMIN role."""
    UserCompanyAccess.objects.filter(user=user, company=company).delete()
    UserStore.objects.filter(user=user, store__company=company).delete()


@transaction.atomic
def set_store_access(user, store, role: str) -> None:
    """Create or update the canonical and selector records for one branch."""
    UserStore.objects.update_or_create(
        user=user,
        store=store,
        defaults={"role": role, "is_active": True},
    )
    UserCompanyAccess.objects.get_or_create(
        user=user,
        company=store.company,
        store=store,
        defaults={"is_default": False},
    )
