from django.urls import path

from apps.api.v1.catalog.views import (
    CatalogProductDetailAPIView,
    CatalogProductListAPIView,
    PrivateCatalogProductDetailAPIView,
    PrivateCatalogProductListAPIView,
)

urlpatterns = [
    path("catalog/products/", CatalogProductListAPIView.as_view(), name="api_v1_catalog_products"),
    path("catalog/products/<uuid:pk>/detail/", CatalogProductDetailAPIView.as_view(), name="api_v1_catalog_product_detail"),
    path("catalog/private/products/", PrivateCatalogProductListAPIView.as_view(), name="api_v1_private_catalog_products"),
    path("catalog/private/products/<uuid:pk>/detail/", PrivateCatalogProductDetailAPIView.as_view(), name="api_v1_private_catalog_product_detail"),
]
