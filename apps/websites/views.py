from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import IntegrityError
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from . import domain_services
from .forms import WebsiteDomainForm
from .models import Website
from .permissions import website_capabilities, require_website_permission


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def website_management(request):
    context = {"user": request.user, "company_id": request.active_company_id, "store_id": request.active_store_id}
    _, capabilities = website_capabilities(**context)
    require_website_permission(**context, permission="view")
    website = Website.objects.filter(company_id=request.active_company_id).first()
    form = WebsiteDomainForm()
    if request.method == "POST":
        operation = request.POST.get("operation")
        try:
            if operation == "create":
                domain_services.create_company_website(**context)
            elif website is None:
                raise Http404
            elif operation == "register":
                require_website_permission(**context, permission="domains")
                form = WebsiteDomainForm(request.POST)
                if form.is_valid():
                    domain_services.register_domain(**context, website_id=website.pk, **form.cleaned_data)
                else:
                    return render(request, "websites/management.html", {"website": website, "capabilities": capabilities, "form": form, "domains": website.domains.all(), "active_tab": "websites"}, status=400)
            else:
                domain_services.change_domain(**context, website_id=website.pk, domain_id=request.POST.get("domain_id"), operation=operation, evidence=request.POST.get("evidence", ""))
        except ObjectDoesNotExist as exc:
            raise Http404 from exc
        except (ValidationError, IntegrityError) as exc:
            messages.error(request, " ".join(exc.messages) if isinstance(exc, ValidationError) else "El dominio ya existe o entró en conflicto con otra operación.")
        else:
            messages.success(request, "Configuración guardada. Esta acción no publica contenido del Website.")
        return redirect("websites:management")
    return render(request, "websites/management.html", {"website": website, "capabilities": capabilities, "form": form, "domains": website.domains.all() if website else [], "active_tab": "websites"})
