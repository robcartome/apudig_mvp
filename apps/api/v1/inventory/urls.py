from django.urls import path

from apps.api.v1.inventory.views import ProductDetailAPIView, ProductListAPIView

urlpatterns = [
    path("products/", ProductListAPIView.as_view(), name="api_v1_products_list"),
    path("products/<uuid:pk>/", ProductDetailAPIView.as_view(), name="api_v1_products_detail"),
]
