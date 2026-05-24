"""
companies/context_processors.py

Inyecta la empresa y sucursal activa en el contexto de todos los templates.
Requiere que ActiveCompanyMiddleware haya procesado el request antes.
"""
from .models import Company, Store


def active_company_context(request):
    """
    Variables disponibles en todos los templates:
    - active_company: objeto Company o None
    - active_store:   objeto Store o None
    """
    ctx = {
        "active_company": None,
        "active_store": None,
        "available_accesses": [],
        "active_access_id": None,
    }

    if not request.user.is_authenticated:
        return ctx

    company_id = getattr(request, "active_company_id", None)
    store_id = getattr(request, "active_store_id", None)

    if company_id:
        ctx["active_company"] = Company.objects.filter(pk=company_id).first()
    if store_id:
        ctx["active_store"] = Store.objects.filter(pk=store_id).first()

    accesses = (
        request.user.company_accesses.select_related("company", "store")
        .order_by("-is_default", "company__name", "store__name")
    )
    ctx["available_accesses"] = accesses

    if company_id:
        selected = accesses.filter(company_id=company_id, store_id=store_id).first()
        if not selected:
            selected = accesses.filter(company_id=company_id, store__isnull=True).first()
        if selected:
            ctx["active_access_id"] = str(selected.id)

    return ctx
