from django.db.models import DecimalField, Q, Sum
from django.db.models.functions import Coalesce
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, permissions

from apps.api.v1.base import BaseCompanyAPIView
from apps.api.v1.inventory.serializers import ProductDetailSerializer, ProductListSerializer
from apps.inventory import selectors as inventory_selectors


class ProductListAPIView(BaseCompanyAPIView, generics.ListAPIView):
    serializer_class = ProductListSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Inventory"],
        summary="List products",
        description="List products with optional search, brand/category filters and limit/offset pagination.",
        parameters=[
            OpenApiParameter(name="search", required=False, type=str, description="Search by name or SKU."),
            OpenApiParameter(name="brand", required=False, type=str, description="Filter by brand UUID."),
            OpenApiParameter(name="category", required=False, type=str, description="Filter by category UUID."),
            OpenApiParameter(name="limit", required=False, type=int, description="Pagination size (max 100)."),
            OpenApiParameter(name="offset", required=False, type=int, description="Pagination offset."),
        ],
        responses={200: ProductListSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        company_id = self.get_company_id()
        search = (self.request.query_params.get("search") or "").strip()
        brand = (self.request.query_params.get("brand") or "").strip()
        category = (self.request.query_params.get("category") or "").strip()

        qs = inventory_selectors.get_products(company_id=company_id, active_only=True)
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(sku__icontains=search))
        if brand:
            qs = qs.filter(brand_id=brand)
        if category:
            qs = qs.filter(category_id=category)

        return qs.annotate(
            stock=Coalesce(Sum("stocks__quantity"), 0, output_field=DecimalField(max_digits=14, decimal_places=3))
        )


class ProductDetailAPIView(BaseCompanyAPIView, generics.RetrieveAPIView):
    serializer_class = ProductDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "pk"

    @extend_schema(
        tags=["Inventory"],
        summary="Retrieve product",
        description="Retrieve a single product including price-list values and stock by warehouse.",
        responses={200: ProductDetailSerializer},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        company_id = self.get_company_id()
        return (
            inventory_selectors.get_products(company_id=company_id, active_only=True)
            .prefetch_related("prices__price_list", "stocks__warehouse")
        )
