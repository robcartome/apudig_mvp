from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .services import get_user_accessible_companies, set_active_session


@login_required
def select_company(request):
    accesses = get_user_accessible_companies(request.user)

    if request.method == "POST":
        access_id = request.POST.get("access_id")
        selected = next((a for a in accesses if a.id == access_id), None)
        if selected:
            set_active_session(request, selected)
            return redirect("dashboard")

    return render(request, "web/select_company.html", {"accesses": accesses})
