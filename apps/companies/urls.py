from django.urls import path

from .views import select_company

urlpatterns = [
    path("select/", select_company, name="select_company"),
]
