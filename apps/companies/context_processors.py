"""
companies/context_processors.py

Inyecta la empresa y sucursal activa en el contexto de todos los templates.
Requiere que ActiveCompanyMiddleware haya procesado el request antes.
"""
from .models import Company, CompanyBranding, Store
from .selectors import get_user_selectable_accesses


def active_company_context(request):
    """
    Variables disponibles en todos los templates:
    - active_company:      objeto Company o None
    - active_store:        objeto Store o None
    - active_branding:     objeto CompanyBranding o None
    - available_accesses:  lista de UserCompanyAccess filtrada (sin duplicados)
    - active_access_id:    str UUID del acceso activo o None
    """
    ctx = {
        "active_company": None,
        "active_store": None,
        "active_branding": None,
        "available_accesses": [],
        "active_access_id": None,
        "can_manage_company": False,
        "active_store_role": None,
    }

    if not request.user.is_authenticated:
        return ctx

    company_id = getattr(request, "active_company_id", None)
    store_id = getattr(request, "active_store_id", None)

    if company_id:
        ctx["active_company"] = Company.objects.filter(pk=company_id).first()
        ctx["active_branding"] = CompanyBranding.objects.filter(company_id=company_id).first()
    if store_id:
        ctx["active_store"] = Store.objects.filter(pk=store_id).first()

    from apps.users.permissions import user_is_company_admin, user_store_role

    ctx["can_manage_company"] = user_is_company_admin(request.user, company_id)
    ctx["active_store_role"] = user_store_role(request.user, company_id, store_id)

    all_accesses = list(get_user_selectable_accesses(request.user))
    ctx["available_accesses"] = all_accesses

    # Determinar el acceso activo (puede ser a nivel empresa o sucursal)
    if company_id:
        selected = next(
            (a for a in all_accesses
             if str(a.company_id) == str(company_id)
             and (str(a.store_id) if a.store_id else None) == store_id),
            None
        )
        if selected:
            ctx["active_access_id"] = str(selected.id)

    return ctx
