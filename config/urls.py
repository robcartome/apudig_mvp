from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("apps.web.urls")),
    path("companies/", include("apps.companies.urls")),
    path("users/", include("apps.users.urls")),
    path("partners/", include("apps.partners.urls")),
    path("inventory/", include("apps.inventory.urls")),
    path("sales/", include("apps.sales.urls")),
]
