"""
users/services.py — Lógica de negocio de usuarios, roles y permisos.
"""
from django.contrib.auth import get_user_model
from django.db import transaction

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
