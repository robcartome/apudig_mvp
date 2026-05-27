from django.urls import path

from .auth_api import obtain_token, refresh_token

app_name = "api_auth"

urlpatterns = [
    path("token/", obtain_token, name="token_obtain"),
    path("token/refresh/", refresh_token, name="token_refresh"),
]
