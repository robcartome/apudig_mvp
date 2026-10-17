from django.contrib.auth.decorators import login_required
import mimetypes

from django.http import FileResponse, Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Company, CompanyBranding, Store, UserCompanyAccess
from .logo_images import normalized_logo_stream
from .selectors import get_user_selectable_accesses


def _safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return None


def select_company_context(request):
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

    accesses = get_user_selectable_accesses(request.user)

    # If there is only one possible context, auto-select it and continue.
    if request.method == "GET" and accesses.count() == 1:
        only_access = accesses.first()
        request.session["active_company_id"] = str(only_access.company_id)
        request.session["active_store_id"] = str(only_access.store_id) if only_access.store_id else None
        return redirect(_safe_next_url(request) or "dashboard")

    if request.method == "POST":
        access_id = request.POST.get("access_id")
        if not access_id:
            return HttpResponseBadRequest("Debes seleccionar una empresa/sucursal.")
        selected = get_object_or_404(accesses, id=access_id)
        request.session["active_company_id"] = str(selected.company_id)
        request.session["active_store_id"] = str(selected.store_id) if selected.store_id else None

        next_url = _safe_next_url(request)
        if next_url:
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
            "next": _safe_next_url(request),
        },
    )


@login_required
def select_company(request):
    return select_company_context(request)


@login_required
def branding_logo(request, pk):
    """Entrega el logo cargado sin publicar el resto de MEDIA_ROOT."""
    from apps.users.permissions import user_can_access_context

    if not user_can_access_context(request.user, pk):
        raise Http404
    branding = get_object_or_404(CompanyBranding, company_id=pk)
    if not branding.logo_file:
        raise Http404
    branding.logo_file.open("rb")
    try:
        logo_stream = normalized_logo_stream(branding.logo_file)
        branding.logo_file.close()
        content_type = "image/png"
    except (OSError, ValueError):
        branding.logo_file.seek(0)
        logo_stream = branding.logo_file
        content_type = mimetypes.guess_type(branding.logo_file.name)[0] or "application/octet-stream"
    response = FileResponse(logo_stream, content_type=content_type)
    response["Cache-Control"] = "private, max-age=3600"
    return response
