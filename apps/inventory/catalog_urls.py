from django.urls import path

from .views.catalog_api import catalog_product_detail, catalog_products

urlpatterns = [
    path("products", catalog_products, name="catalog_products"),
    path("products/<uuid:product_id>/detail", catalog_product_detail, name="catalog_product_detail"),
]