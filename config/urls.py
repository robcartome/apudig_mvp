from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.web.views import logout_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", logout_view, name="logout"),
    # ── API endpoints for Next.js frontend ────────────────────────────────────
    path("api/auth/", include("apps.users.auth_api_urls")),
    path("catalog/", include("apps.inventory.catalog_urls")),
    path("", include("apps.web.urls")),
    path("companies/", include("apps.companies.urls")),
    path("management/", include("apps.users.urls")),
    path("partners/", include("apps.partners.urls")),
    path("inventory/", include("apps.inventory.urls")),
    path("sales/", include("apps.sales.urls")),
]
