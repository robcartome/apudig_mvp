from django.urls import path

from apps.api.v1.users.views import TokenObtainAPIView, TokenRefreshAPIView

urlpatterns = [
    path("auth/token/", TokenObtainAPIView.as_view(), name="api_v1_token_obtain"),
    path("auth/refresh/", TokenRefreshAPIView.as_view(), name="api_v1_token_refresh"),
]
