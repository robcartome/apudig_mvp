from decimal import Decimal

from django.db.models import DecimalField, OuterRef, Prefetch, Subquery, Sum
from django.db.models.functions import Coalesce
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, permissions

from apps.api.v1.base import BaseCompanyAPIView
from apps.api.v1.catalog.pagination import CatalogLegacyPagination
from apps.api.v1.catalog.serializers import (
    CatalogProductDetailSerializer,
    CatalogProductListSerializer,
)
from apps.inventory import selectors as inventory_selectors
from apps.inventory.models import ProductSupplier, StockByWarehouse


def _active_supplier_codes_prefetch():
    return Prefetch(
        "supplier_relations",
        queryset=(
            ProductSupplier.objects.filter(active=True)
            .exclude(supplier_code="")
            .only("product_id", "supplier_code")
            .order_by("supplier_code")
        ),
        to_attr="active_supplier_code_relations",
    )


class CatalogProductListAPIView(BaseCompanyAPIView, generics.ListAPIView):
    serializer_class = CatalogProductListSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = CatalogLegacyPagination
    company_required = False

    def get_queryset(self):
        company_id = self.get_company_id()
        search = (self.request.query_params.get("search") or "").strip()
        brand = (self.request.query_params.get("brand") or "").strip()
        category = (self.request.query_params.get("category") or "").strip()

        qs = inventory_selectors.search_products(
            search, company_id=company_id, active_only=True
        ).prefetch_related(_active_supplier_codes_prefetch())
        if brand:
            qs = qs.filter(brand_id=brand)
        if category:
            qs = qs.filter(category_id=category)

        stock_subquery = Subquery(
            StockByWarehouse.objects
            .filter(product=OuterRef("pk"))
            .values("product")
            .annotate(total=Sum("quantity"))
            .values("total")[:1],
            output_field=DecimalField(max_digits=14, decimal_places=3),
        )
        return qs.annotate(
            stock=Coalesce(stock_subquery, Decimal("0"), output_field=DecimalField(max_digits=14, decimal_places=3))
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["include_purchase_price"] = False
        return context

    @extend_schema(
        tags=["Catalog"],
        summary="Public product catalog",
        description="Public catalog searchable by internal or active supplier product codes. price_purchase is omitted unless the request is authenticated.",
        parameters=[
            OpenApiParameter(
                name="search", required=False, type=str,
                description="Search by name, SKU, barcode, model, supplier code or supplier product name.",
            ),
            OpenApiParameter(name="brand", required=False, type=str),
            OpenApiParameter(name="category", required=False, type=str),
            OpenApiParameter(name="limit", required=False, type=int),
            OpenApiParameter(name="offset", required=False, type=int),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class CatalogProductDetailAPIView(BaseCompanyAPIView, generics.RetrieveAPIView):
    serializer_class = CatalogProductDetailSerializer
    permission_classes = [permissions.AllowAny]
    company_required = False

    def get_queryset(self):
        company_id = self.get_company_id()
        qs = inventory_selectors.get_products(
            company_id=company_id, active_only=True
        ).prefetch_related(
            "prices__price_list",
            "stocks__warehouse",
            _active_supplier_codes_prefetch(),
        )
        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["include_purchase_price"] = False
        return context

    @extend_schema(
        tags=["Catalog"],
        summary="Public product detail",
        description="Product detail including active supplier codes. price_purchase is omitted unless the request is authenticated.",
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


class PrivateCatalogProductListAPIView(CatalogProductListAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["include_purchase_price"] = True
        return context


class PrivateCatalogProductDetailAPIView(CatalogProductDetailAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["include_purchase_price"] = True
        return context
