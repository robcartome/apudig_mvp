from django.http import JsonResponse
from django.urls import path


def not_implemented(_request):
    return JsonResponse({"detail": "API v2 not implemented yet."}, status=501)


urlpatterns = [
    path("", not_implemented, name="api_v2_placeholder"),
]
