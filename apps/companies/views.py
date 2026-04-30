from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .models import Company, Store, UserCompanyAccess


@login_required
def select_company(request):
    accesses = (
        UserCompanyAccess.objects.select_related("company", "store")
        .filter(user=request.user)
        .order_by("-is_default", "company__name")
    )

    if request.method == "POST":
        access_id = request.POST.get("access_id")
        selected = get_object_or_404(accesses, id=access_id)
        request.session["active_company_id"] = selected.company_id
        request.session["active_store_id"] = selected.store_id
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
