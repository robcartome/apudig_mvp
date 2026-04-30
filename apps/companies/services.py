"""
companies/services.py — Lógica de negocio de empresas y sucursales.

Reglas:
- Toda operación que modifique datos o cruce más de un modelo va aquí.
- Las vistas solo coordinan HTTP; nunca ponen lógica de negocio.
"""
from dataclasses import dataclass

from django.db import transaction


@dataclass
class CompanyAccessOption:
    """
    DTO inmutable que representa una opción empresa/sucursal
    disponible para un usuario en la pantalla de selección.
    Desacopla la vista del modelo subyacente (UserStore o UserCompanyAccess).
    """
    id: str              # UUID como string (clave del <option> en el formulario)
    company_id: str
    company_name: str
    store_id: str | None
    store_name: str | None
    is_default: bool = False


def get_user_accessible_companies(user) -> list[CompanyAccessOption]:
    """
    Devuelve las opciones empresa/sucursal accesibles para el usuario.

    Prioridad:
    1. UserStore — modelo de autorización real derivado de roles por sucursal.
    2. UserCompanyAccess — tabla auxiliar transitoria (fallback).
    """
    from apps.users.models import UserStore
    from .models import UserCompanyAccess

    options: list[CompanyAccessOption] = []

    # 1. Acceso real desde UserStore
    user_stores = (
        UserStore.objects
        .select_related("store", "store__company")
        .filter(user=user, is_active=True)
        .order_by("store__company__name", "store__name")
    )
    for us in user_stores:
        options.append(CompanyAccessOption(
            id=str(us.id),
            company_id=str(us.store.company_id),
            company_name=us.store.company.name,
            store_id=str(us.store_id),
            store_name=us.store.name,
        ))

    # 2. Fallback: UserCompanyAccess (tabla transitoria)
    if not options:
        for uca in (
            UserCompanyAccess.objects
            .select_related("company", "store")
            .filter(user=user)
            .order_by("-is_default", "company__name")
        ):
            options.append(CompanyAccessOption(
                id=str(uca.id),
                company_id=str(uca.company_id),
                company_name=uca.company.name,
                store_id=str(uca.store_id) if uca.store_id else None,
                store_name=uca.store.name if uca.store else None,
                is_default=uca.is_default,
            ))

    return options


def set_active_session(request, access: CompanyAccessOption) -> None:
    """Persiste empresa y sucursal activa en la sesión del request."""
    request.session["active_company_id"] = access.company_id
    request.session["active_store_id"] = access.store_id

