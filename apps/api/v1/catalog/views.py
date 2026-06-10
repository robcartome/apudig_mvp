from decimal import Decimal

from django.db.models import DecimalField, Q, Sum
from django.db.models.functions import Coalesce
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, permissions

from apps.api.v1.base import BaseCompanyAPIView
from apps.api.v1.catalog.pagination import CatalogLegacyPagination
from apps.api.v1.catalog.serializers import (
    CatalogProductDetailSerializer,
    CatalogProductListSerializer,
)
from apps.inventory.models import Product


class CatalogProductListAPIView(BaseCompanyAPIView, generics.ListAPIView):
    serializer_class = CatalogProductListSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = CatalogLegacyPagination
    company_required = False

    def get_queryset(self):
        company_id = self.get_company_id()
        qs = Product.objects.filter(active=True).select_related("unit", "brand", "category")
        if company_id:
            qs = qs.filter(company_id=company_id)

        search = (self.request.query_params.get("search") or "").strip()
        brand = (self.request.query_params.get("brand") or "").strip()
        category = (self.request.query_params.get("category") or "").strip()

        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(sku__icontains=search))
        if brand:
            qs = qs.filter(brand_id=brand)
        if category:
            qs = qs.filter(category_id=category)

        return qs.annotate(
            stock=Coalesce(
                Sum("stocks__quantity"),
                Decimal("0"),
                output_field=DecimalField(max_digits=14, decimal_places=3),
            )
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["include_purchase_price"] = False
        return context

    @extend_schema(
        tags=["Catalog"],
        summary="Public product catalog",
        description="Public catalog response compatible with the current frontend structure. price_purchase is omitted unless the request is authenticated.",
        parameters=[
            OpenApiParameter(name="search", required=False, type=str),
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
        qs = Product.objects.filter(active=True).select_related("unit", "brand", "category").prefetch_related(
            "prices__price_list",
            "stocks__warehouse",
        )
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["include_purchase_price"] = False
        return context

    @extend_schema(
        tags=["Catalog"],
        summary="Public product detail",
        description="Product detail compatible with the current frontend structure. price_purchase is omitted unless the request is authenticated.",
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
