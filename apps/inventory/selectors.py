"""
inventory/selectors.py — Consultas de lectura de inventario.
"""
from django.db.models import Q

from .models import Brand, Category, Movement, PriceList, Product, ProductPrice, StockByWarehouse, Unit, Warehouse


# ── Maestros ──────────────────────────────────────────────────────────────────

def get_categories(company_id=None, active_only: bool = False):
    qs = Category.objects.for_company(company_id) if company_id else Category.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    return qs.order_by("name")


def search_categories(query: str, company_id=None, active_only: bool = False):
    qs = get_categories(company_id=company_id, active_only=active_only)
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(code__icontains=query))
    return qs


def get_brands(company_id=None, active_only: bool = False):
    qs = Brand.objects.for_company(company_id) if company_id else Brand.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    return qs.order_by("name")


def search_brands(query: str, company_id=None, active_only: bool = False):
    qs = get_brands(company_id=company_id, active_only=active_only)
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
    qs = Warehouse.objects.for_store(store_id)
    if active_only:
        qs = qs.filter(active=True)
    return qs.select_related("store").order_by("name")


def search_warehouses(store_id: str, query: str, active_only: bool = False):
    qs = get_warehouses_for_store(store_id, active_only=active_only)
    if query:
        qs = qs.filter(name__icontains=query)
    return qs


# ── Productos ─────────────────────────────────────────────────────────────────

def get_products(company_id=None, active_only: bool = False):
    qs = Product.objects.select_related("category", "brand", "unit")
    if company_id:
        qs = qs.for_company(company_id)
    if active_only:
        qs = qs.filter(active=True)
    return qs.order_by("name")


def search_products(query: str, company_id=None, active_only: bool = False):
    qs = get_products(company_id=company_id, active_only=active_only)
    if query:
        qs = qs.filter(
            Q(name__icontains=query) | Q(sku__icontains=query) | Q(barcode__icontains=query)
        )
    return qs


# ── Listas de precio ─────────────────────────────────────────────────────────

def get_price_lists(company_id=None, active_only: bool = False):
    qs = PriceList.objects.for_company(company_id) if company_id else PriceList.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    return qs.order_by("name")


def search_price_lists(query: str, company_id=None, active_only: bool = False):
    qs = get_price_lists(company_id=company_id, active_only=active_only)
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


def get_price_consolidate(company_id, query: str = ""):
    """Returns (price_lists, rows) for the consolidated price report.

    price_lists  — list of PriceList objects ordered by name.
    rows         — list of dicts:
        {sku, name, price_purchase, price_sale, prices: {str(pl_pk): Decimal|None}}
    """
    price_lists = list(
        PriceList.objects.filter(company_id=company_id, active=True).order_by("name")
    )
    pl_ids = [pl.pk for pl in price_lists]

    qs = Product.objects.filter(company_id=company_id, active=True)
    if query:
        qs = qs.filter(
            Q(sku__icontains=query)
            | Q(name__icontains=query)
            | Q(barcode__icontains=query)
        )
    qs = qs.order_by("sku")
    products = list(qs)

    product_ids = [p.pk for p in products]
    price_map: dict[tuple, object] = {}
    if product_ids and pl_ids:
        for pp in ProductPrice.objects.filter(
            product_id__in=product_ids,
            price_list_id__in=pl_ids,
        ).values("product_id", "price_list_id", "amount"):
            price_map[(str(pp["product_id"]), str(pp["price_list_id"]))] = pp["amount"]

    rows = [
        {
            "sku": p.sku,
            "name": p.name,
            "price_purchase": p.price_purchase,
            "price_sale": p.price_sale,
            "prices": {
                str(pl.pk): price_map.get((str(p.pk), str(pl.pk)))
                for pl in price_lists
            },
        }
        for p in products
    ]
    return price_lists, rows


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
        Movement.objects.for_store(store_id)
        .select_related("store", "warehouse", "warehouse_origin", "warehouse_dest",
                        "supplier", "customer", "document_type", "created_by")
        .prefetch_related("details__product__unit")
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
        .prefetch_related("details__product__unit", "audit_logs__changed_by")
        .select_related("store", "warehouse", "warehouse_origin", "warehouse_dest",
                        "supplier", "customer", "carrier", "document_type", "created_by", "confirmed_by", "closed_by")
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

