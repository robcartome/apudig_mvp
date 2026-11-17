from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, permissions
from apps.api.v1.base import BaseCompanyAPIView
from .access import CatalogAccessMixin
from .selectors import catalog_products, filter_catalog_products
from .pagination import CatalogLegacyPagination
from .serializers import (
    BasicCatalogProductDetailSerializer,
    BasicCatalogProductListSerializer,
    CatalogProductDetailSerializer,
    CatalogProductListSerializer,
)


class CatalogProductListAPIView(CatalogAccessMixin, BaseCompanyAPIView, generics.ListAPIView):
    require_product_permission = False
    serializer_class = BasicCatalogProductListSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CatalogLegacyPagination
    company_required = True

    def get_queryset(self):
        search = (self.request.query_params.get("search") or "").strip()
        brand = (self.request.query_params.get("brand") or "").strip()
        category = (self.request.query_params.get("category") or "").strip()

        qs = catalog_products(self.catalog_access, search, include_private=self.private_catalog)
        return filter_catalog_products(qs, self.catalog_access, brand=brand, category=category)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["include_purchase_price"] = False
        return context

    @extend_schema(
        tags=["Catalog"],
        summary="Authenticated worker product catalog",
        description="Company-scoped worker catalog. Private fields require the private endpoint and company administration.",
        parameters=[
            OpenApiParameter(
                name="search", required=False, type=str,
                description="Search by name, SKU, barcode or model. Supplier search is available only on the private endpoint.",
            ),
            OpenApiParameter(name="brand", required=False, type=str),
            OpenApiParameter(name="category", required=False, type=str),
            OpenApiParameter(name="limit", required=False, type=int),
            OpenApiParameter(name="offset", required=False, type=int),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class CatalogProductDetailAPIView(CatalogAccessMixin, BaseCompanyAPIView, generics.RetrieveAPIView):
    require_product_permission = False
    serializer_class = BasicCatalogProductDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    company_required = True

    def get_queryset(self):
        return catalog_products(self.catalog_access, include_private=self.private_catalog)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["include_purchase_price"] = False
        return context

    @extend_schema(
        tags=["Catalog"],
        summary="Authenticated worker product detail",
        description="Company-scoped basic product detail without internal lists, suppliers or warehouse details.",
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


class PrivateCatalogProductListAPIView(CatalogProductListAPIView):
    serializer_class = CatalogProductListSerializer
    private_catalog = True
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["include_purchase_price"] = True
        return context


class PrivateCatalogProductDetailAPIView(CatalogProductDetailAPIView):
    serializer_class = CatalogProductDetailSerializer
    private_catalog = True
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["include_purchase_price"] = True
        return context
