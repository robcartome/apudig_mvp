from django.urls import include, path

urlpatterns = [
    path("", include("apps.api.v1.catalog.urls")),
    path("", include("apps.api.v1.inventory.urls")),
    path("", include("apps.api.v1.users.urls")),
    path("sales/", include("apps.api.v1.sales.urls")),
    path("billing/", include("apps.api.v1.billing.urls")),
    path("companies/", include("apps.api.v1.companies.urls")),
]
