from django.urls import path

from .views import (
    CatalogProductOptionsAPIView, CatalogSettingsAPIView, PublicBrandListAPIView,
    PublicCategoryListAPIView, PublicProductDetailAPIView, PublicProductListAPIView,
    WebsitePublicationDetailAPIView, WebsitePublicationListAPIView,
)


urlpatterns = [
    path("storefront/sites/<str:hostname>/products/", PublicProductListAPIView.as_view(), name="api_v1_storefront_products"),
    path("storefront/sites/<str:hostname>/products/<uuid:product_id>/", PublicProductDetailAPIView.as_view(), name="api_v1_storefront_product"),
    path("storefront/sites/<str:hostname>/categories/", PublicCategoryListAPIView.as_view(), name="api_v1_storefront_categories"),
    path("storefront/sites/<str:hostname>/brands/", PublicBrandListAPIView.as_view(), name="api_v1_storefront_brands"),
    path("websites/<uuid:website_id>/catalog-product-options/", CatalogProductOptionsAPIView.as_view(), name="api_v1_website_catalog_options"),
    path("websites/<uuid:website_id>/catalog-settings/", CatalogSettingsAPIView.as_view(), name="api_v1_website_catalog_settings"),
    path("websites/<uuid:website_id>/products/", WebsitePublicationListAPIView.as_view(), name="api_v1_website_publications"),
    path("websites/<uuid:website_id>/products/<uuid:publication_id>/", WebsitePublicationDetailAPIView.as_view(), name="api_v1_website_publication"),
]
