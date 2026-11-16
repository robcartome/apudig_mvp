from django.urls import path
from .views import website_management

app_name = "websites"
urlpatterns = [path("", website_management, name="management")]
