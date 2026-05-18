"""
inventory/selectors.py — Consultas de lectura de inventario.
"""
from django.db.models import Q

from .models import Brand, Category, Movement, PriceList, Product, ProductPrice, StockByWarehouse, Unit, Warehouse


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


# ── Listas de precio ─────────────────────────────────────────────────────────

def get_price_lists(active_only: bool = False):
    qs = PriceList.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    return qs.order_by("name")


def search_price_lists(query: str, active_only: bool = False):
    qs = get_price_lists(active_only=active_only)
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(description__icontains=query))
    return qs


def get_pricelist_detail(pk):
    """PriceList con sus precios prefetchados (product + unit)."""
    return PriceList.objects.prefetch_related(
        "product_prices__product__unit",
        "product_prices__product__category",
    ).get(pk=pk)


def get_product_price(pricelist_id, product_id):
    """Retorna ProductPrice o None."""
    try:
        return ProductPrice.objects.select_related("product", "price_list").get(
            price_list_id=pricelist_id, product_id=product_id
        )
    except ProductPrice.DoesNotExist:
        return None


# ── Stock ─────────────────────────────────────────────────────────────────────

def get_stock_by_warehouse(store_id: str):
    """Stock de todos los productos agrupado por almacén para una sucursal."""
    return (
        StockByWarehouse.objects
        .select_related("product", "product__unit", "warehouse")
        .filter(warehouse__store_id=store_id)
        .order_by("warehouse__name", "product__name")
    )

def get_movements_for_store(store_id: str, movement_type: str | None = None):
    qs = (
        Movement.objects
        .select_related("warehouse", "warehouse_origin", "warehouse_dest",
                        "supplier", "customer", "document_type", "created_by")
        .prefetch_related("details__product__unit")
        .filter(store_id=store_id)
    )
    if movement_type:
        qs = qs.filter(type=movement_type)
    return qs.order_by("-date")


def search_movements(store_id: str, query: str, movement_type: str | None = None):
    qs = get_movements_for_store(store_id, movement_type=movement_type)
    if query:
        qs = qs.filter(
            Q(number__icontains=query)
            | Q(reason__icontains=query)
            | Q(reference_doc__icontains=query)
        )
    return qs


def get_movement_detail(pk):
    return (
        Movement.objects
        .prefetch_related("details__product__unit")
        .select_related("warehouse", "warehouse_origin", "warehouse_dest",
                        "supplier", "customer", "carrier", "document_type", "created_by")
        .get(pk=pk)
    )


def get_stock_for_product(product_id, store_id: str):
    """Retorna la cantidad total en stock para un producto en una sucursal."""
    from django.db.models import Sum
    result = (
        StockByWarehouse.objects
        .filter(product_id=product_id, warehouse__store_id=store_id)
        .aggregate(total=Sum("quantity"))
    )
    from decimal import Decimal
    return result["total"] or Decimal("0")

