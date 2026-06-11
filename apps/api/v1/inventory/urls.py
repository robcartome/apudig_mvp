from django.urls import path

from apps.api.v1.inventory.views import (
    BrandListAPIView,
    CategoryListAPIView,
    DocumentTypeListAPIView,
    ProductDetailAPIView,
    ProductListAPIView,
    UnitListAPIView,
    WarehouseDetailAPIView,
    WarehouseListAPIView,
)

urlpatterns = [
    path("categories/", CategoryListAPIView.as_view(), name="api_v1_categories_list"),
    path("brands/", BrandListAPIView.as_view(), name="api_v1_brands_list"),
    path("units/", UnitListAPIView.as_view(), name="api_v1_units_list"),
    path("warehouses/", WarehouseListAPIView.as_view(), name="api_v1_warehouses_list"),
    path("warehouses/<uuid:pk>/", WarehouseDetailAPIView.as_view(), name="api_v1_warehouses_detail"),
    path("document-types/", DocumentTypeListAPIView.as_view(), name="api_v1_document_types_list"),
    path("products/", ProductListAPIView.as_view(), name="api_v1_products_list"),
    path("products/<uuid:pk>/", ProductDetailAPIView.as_view(), name="api_v1_products_detail"),
]
