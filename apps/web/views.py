from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


@login_required
def home(request):
    return redirect("dashboard")


@login_required
def dashboard(request):
    if not request.active_company_id:
        return redirect("select_company")

    return render(
        request,
        "web/dashboard.html",
        {
            "active_company_id": request.active_company_id,
            "active_store_id": request.active_store_id,
        },
    )
