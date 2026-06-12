from django.db.models import DecimalField, Q, Sum
from django.db.models.functions import Coalesce
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response

from apps.api.v1.base import BaseCompanyAPIView
from apps.api.v1.inventory.serializers import (
    CategorySerializer,
    BrandSerializer,
    DocumentTypeSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    UnitSerializer,
    WarehouseSerializer,
    WarehouseUpdateSerializer,
)
from apps.inventory import selectors as inventory_selectors
from apps.inventory.models import Warehouse
from apps.partners.models import DocumentType


def _get_store_id_from_request(request):
    if isinstance(request.auth, dict):
        store_id = request.auth.get("store_id")
        if store_id:
            return store_id
    raw_request = getattr(request, "_request", None)
    if raw_request is not None:
        store_id = getattr(raw_request, "active_store_id", None)
        if store_id:
            return store_id
        session = getattr(raw_request, "session", None)
        if session is not None:
            return session.get("active_store_id")
    return None


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


class CategoryListAPIView(BaseCompanyAPIView, generics.ListAPIView):
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Inventory"], summary="List categories")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        company_id = self.get_company_id()
        active_only = (self.request.query_params.get("active_only") or "true").lower() != "false"
        query = (self.request.query_params.get("search") or "").strip()
        qs = inventory_selectors.get_categories(company_id=company_id, active_only=active_only)
        if query:
            qs = qs.filter(Q(name__icontains=query) | Q(code__icontains=query))
        return qs


class BrandListAPIView(BaseCompanyAPIView, generics.ListAPIView):
    serializer_class = BrandSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Inventory"], summary="List brands")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        company_id = self.get_company_id()
        active_only = (self.request.query_params.get("active_only") or "true").lower() != "false"
        query = (self.request.query_params.get("search") or "").strip()
        qs = inventory_selectors.get_brands(company_id=company_id, active_only=active_only)
        if query:
            qs = qs.filter(name__icontains=query)
        return qs


class UnitListAPIView(generics.ListAPIView):
    serializer_class = UnitSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Inventory"], summary="List units")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        query = (self.request.query_params.get("search") or "").strip()
        qs = inventory_selectors.get_units()
        if query:
            qs = qs.filter(Q(code__icontains=query) | Q(name__icontains=query))
        return qs


class WarehouseListAPIView(BaseCompanyAPIView, generics.ListAPIView):
    serializer_class = WarehouseSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Inventory"],
        summary="List warehouses",
        parameters=[
            OpenApiParameter(name="active_only", required=False, type=bool, description="Filter active warehouses."),
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        company_id = self.get_company_id()
        store_id = _get_store_id_from_request(self.request)
        active_only = (self.request.query_params.get("active_only") or "true").lower() != "false"

        if store_id:
            qs = inventory_selectors.get_warehouses_for_store(store_id, active_only=active_only)
        else:
            qs = Warehouse.objects.select_related("store").all().order_by("name")
            if company_id:
                qs = qs.filter(store__company_id=company_id)
            if active_only:
                qs = qs.filter(active=True)
        return qs


class WarehouseDetailAPIView(BaseCompanyAPIView, generics.UpdateAPIView):
    serializer_class = WarehouseUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    @extend_schema(tags=["Inventory"], summary="Update warehouse")
    def put(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def get_queryset(self):
        company_id = self.get_company_id()
        store_id = _get_store_id_from_request(self.request)
        qs = Warehouse.objects.select_related("store")
        if store_id:
            return qs.filter(store_id=store_id)
        if company_id:
            return qs.filter(store__company_id=company_id)
        return qs.none()


class DocumentTypeListAPIView(generics.ListAPIView):
    serializer_class = DocumentTypeSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Inventory"], summary="List document types")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        active_only = (self.request.query_params.get("active_only") or "true").lower() != "false"
        query = (self.request.query_params.get("search") or "").strip()
        qs = DocumentType.objects.all().order_by("code")
        if active_only:
            qs = qs.filter(active=True)
        if query:
            qs = qs.filter(Q(code__icontains=query) | Q(name__icontains=query) | Q(abbreviation__icontains=query))
        return qs
