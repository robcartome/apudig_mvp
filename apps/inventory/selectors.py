"""
inventory/selectors.py — Consultas de lectura de inventario.
"""
from django.db.models import Q

from .models import Brand, Category, Product, StockByWarehouse, Unit, Warehouse


# ── Maestros ──────────────────────────────────────────────────────────────────

def get_categories(active_only: bool = False):
    qs = Category.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    return qs.order_by("name")


def search_categories(query: str, active_only: bool = False):
    qs = get_categories(active_only=active_only)
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(code__icontains=query))
    return qs


def get_brands(active_only: bool = False):
    qs = Brand.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    return qs.order_by("name")


def search_brands(query: str, active_only: bool = False):
    qs = get_brands(active_only=active_only)
    if query:
        qs = qs.filter(name__icontains=query)
    return qs


def get_units():
    return Unit.objects.all().order_by("code")


def search_units(query: str):
    qs = get_units()
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(code__icontains=query))
    return qs


# ── Almacenes ─────────────────────────────────────────────────────────────────

def get_warehouses_for_store(store_id: str, active_only: bool = False):
    qs = Warehouse.objects.filter(store_id=store_id)
    if active_only:
        qs = qs.filter(active=True)
    return qs.select_related("store").order_by("name")


def search_warehouses(store_id: str, query: str, active_only: bool = False):
    qs = get_warehouses_for_store(store_id, active_only=active_only)
    if query:
        qs = qs.filter(name__icontains=query)
    return qs


# ── Productos ─────────────────────────────────────────────────────────────────

def get_products(active_only: bool = False):
    qs = Product.objects.select_related("category", "brand", "unit")
    if active_only:
        qs = qs.filter(active=True)
    return qs.order_by("name")


def search_products(query: str, active_only: bool = False):
    qs = get_products(active_only=active_only)
    if query:
        qs = qs.filter(
            Q(name__icontains=query) | Q(sku__icontains=query) | Q(barcode__icontains=query)
        )
    return qs


# ── Stock ─────────────────────────────────────────────────────────────────────

def get_stock_by_warehouse(store_id: str):
    """Stock de todos los productos agrupado por almacén para una sucursal."""
    return (
        StockByWarehouse.objects
        .select_related("product", "product__unit", "warehouse")
        .filter(warehouse__store_id=store_id)
        .order_by("warehouse__name", "product__name")
    )

