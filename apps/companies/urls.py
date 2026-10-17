from django.urls import path

from .views import branding_logo, select_company

urlpatterns = [
    path("select/", select_company, name="select_company"),
    path("<uuid:pk>/branding/logo/", branding_logo, name="company_branding_logo"),
]
