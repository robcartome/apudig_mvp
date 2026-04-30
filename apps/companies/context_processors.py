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
    ctx = {"active_company": None, "active_store": None}

    if not request.user.is_authenticated:
        return ctx

    company_id = getattr(request, "active_company_id", None)
    store_id = getattr(request, "active_store_id", None)

    if company_id:
        ctx["active_company"] = Company.objects.filter(pk=company_id).first()
    if store_id:
        ctx["active_store"] = Store.objects.filter(pk=store_id).first()

    return ctx
