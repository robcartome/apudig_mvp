from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


@login_required
def home(request):
    return redirect("dashboard")


@login_required
def dashboard(request):
    if not request.active_company_id:
        return redirect("select_company")
    return render(request, "web/dashboard.html")


def logout_view(request):
    # Allow both GET (manual /logout/) and POST (menu action) for a robust UX.
    auth_logout(request)
    return redirect("login")
