from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .models import Company, Store
from .services import get_user_accessible_companies, set_active_session


@login_required
def select_company(request):
    accesses = get_user_accessible_companies(request.user)

    if request.method == "POST":
        access_id = request.POST.get("access_id")
        selected = get_object_or_404(accesses, id=access_id)
        set_active_session(request, selected)
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
