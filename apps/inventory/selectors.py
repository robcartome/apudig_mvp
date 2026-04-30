"""
inventory/selectors.py — Consultas de lectura de inventario.
"""
from django.db.models import F, Sum

from .models import Category, Brand, Product, StockByWarehouse, Warehouse


def get_products(company_id: str | None = None, active_only: bool = True):
    qs = Product.objects.select_related("category", "brand", "unit")
    if active_only:
        qs = qs.filter(active=True)
    return qs.order_by("name")


def search_products(query: str, active_only: bool = True):
    qs = get_products(active_only=active_only)
    if query:
        qs = qs.filter(name__icontains=query) | qs.filter(sku__icontains=query) | qs.filter(barcode__icontains=query)
    return qs


def get_stock_by_warehouse(store_id: str):
    """Stock de todos los productos agrupado por almacén para una sucursal."""
    return (
        StockByWarehouse.objects
        .select_related("product", "product__unit", "warehouse")
        .filter(warehouse__store_id=store_id)
        .order_by("warehouse__name", "product__name")
    )


def get_warehouses_for_store(store_id: str, active_only: bool = True):
    qs = Warehouse.objects.filter(store_id=store_id)
    if active_only:
        qs = qs.filter(active=True)
    return qs.order_by("name")
