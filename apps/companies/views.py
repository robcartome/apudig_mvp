from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Company, Store, UserCompanyAccess


@login_required
def select_company(request):
    # Superusuario: sincronizar siempre con todas las empresas y sucursales activas.
    # Se ejecuta en cada carga del selector para capturar nuevas empresas/sucursales.
    if request.user.is_superuser:
        for company in Company.objects.filter(is_active=True):
            UserCompanyAccess.objects.get_or_create(
                user=request.user, company=company, store=None,
                defaults={"is_default": False},
            )
            for store in Store.objects.filter(company=company, active=True):
                UserCompanyAccess.objects.get_or_create(
                    user=request.user, company=company, store=store,
                    defaults={"is_default": False},
                )

    accesses = UserCompanyAccess.objects.select_related("company", "store").filter(user=request.user)
    accesses = accesses.order_by("-is_default", "company__name", "store__name")

    # If there is only one possible context, auto-select it and continue.
    if request.method == "GET" and accesses.count() == 1:
        only_access = accesses.first()
        request.session["active_company_id"] = str(only_access.company_id)
        request.session["active_store_id"] = str(only_access.store_id) if only_access.store_id else None
        return redirect("dashboard")

    if request.method == "POST":
        access_id = request.POST.get("access_id")
        if not access_id:
            return HttpResponseBadRequest("Debes seleccionar una empresa/sucursal.")
        selected = get_object_or_404(accesses, id=access_id)
        request.session["active_company_id"] = str(selected.company_id)
        request.session["active_store_id"] = str(selected.store_id) if selected.store_id else None

        next_url = request.POST.get("next") or request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("dashboard")

    default_company = Company.objects.filter(id=request.session.get("active_company_id")).first()
    default_store = Store.objects.filter(id=request.session.get("active_store_id")).first()

    return render(
        request,
        "web/select_company.html",
        {
            "accesses": accesses,
            "default_company": default_company,
            "default_store": default_store,
        },
    )
