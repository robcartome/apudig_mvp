"""
companies/services.py — Lógica de negocio de empresas y sucursales.

Reglas:
- Toda operación que modifique datos o cruce más de un modelo va aquí.
- Las vistas solo coordinan HTTP; nunca ponen lógica de negocio.
- Usar transaction.atomic() en operaciones que afecten varias tablas.
"""
from django.db import transaction

from .models import Company, CompanyBranding, Store, UserCompanyAccess


def get_user_accessible_companies(user):
    """
    Devuelve los accesos empresa/sucursal que tiene un usuario,
    ordenados por defecto primero.
    """
    return (
        UserCompanyAccess.objects
        .select_related("company", "store")
        .filter(user=user)
        .order_by("-is_default", "company__name")
    )


@transaction.atomic
def set_active_session(request, access: UserCompanyAccess) -> None:
    """Persiste empresa y sucursal activa en la sesión del request."""
    request.session["active_company_id"] = str(access.company_id)
    request.session["active_store_id"] = str(access.store_id) if access.store_id else None
