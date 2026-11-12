from django.urls import path

from apps.api.v1.catalog.views import (
    CatalogProductDetailAPIView,
    CatalogProductListAPIView,
    PrivateCatalogProductDetailAPIView,
    PrivateCatalogProductListAPIView,
    StorefrontProductDetailAPIView,
    StorefrontProductListAPIView,
    StorefrontResolveAPIView,
    StorefrontCategoryListAPIView,
    StorefrontBrandListAPIView,
    StorefrontCartQuoteAPIView,
)

urlpatterns = [
    path("catalog/products/", CatalogProductListAPIView.as_view(), name="api_v1_catalog_products"),
    path("catalog/products/<uuid:pk>/detail/", CatalogProductDetailAPIView.as_view(), name="api_v1_catalog_product_detail"),
    path("catalog/private/products/", PrivateCatalogProductListAPIView.as_view(), name="api_v1_private_catalog_products"),
    path("catalog/private/products/<uuid:pk>/detail/", PrivateCatalogProductDetailAPIView.as_view(), name="api_v1_private_catalog_product_detail"),
    path("storefront/resolve/", StorefrontResolveAPIView.as_view(), name="api_v1_storefront_resolve"),
    path("storefront/sites/<str:hostname>/products/", StorefrontProductListAPIView.as_view(), name="api_v1_storefront_products"),
    path("storefront/sites/<str:hostname>/products/<str:identifier>/", StorefrontProductDetailAPIView.as_view(), name="api_v1_storefront_product_detail"),
    path("storefront/sites/<str:hostname>/categories/", StorefrontCategoryListAPIView.as_view(), name="api_v1_storefront_categories"),
    path("storefront/sites/<str:hostname>/brands/", StorefrontBrandListAPIView.as_view(), name="api_v1_storefront_brands"),
    path("storefront/sites/<str:hostname>/cart/quote/", StorefrontCartQuoteAPIView.as_view(), name="api_v1_storefront_cart_quote"),
]
