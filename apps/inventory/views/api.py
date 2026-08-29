"""
inventory/views/api.py — JSON API endpoints for inventory UI interactions.
"""
import json
import uuid as uuid_lib

from django.db import transaction
from django.db.models import Exists, OuterRef, Prefetch, Q, Sum
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from apps.partners.models import Customer, Supplier

from ..models import (
    Brand,
    Category,
    Product,
    ProductPrice,
    ProductSupplier,
    ProductUnit,
    StockByWarehouse,
    Unit,
    Warehouse,
    WarehouseLocation,
)


def _get_company_id(request):
    return getattr(request, "active_company_id", None) or request.session.get("active_company_id")


def _get_store_id(request):
    return getattr(request, "active_store_id", None) or request.session.get("active_store_id")


def _require_auth(request):
    return not request.user.is_authenticated


@require_GET
def product_search(request):
    """Return up to 50 products matching `q`, scoped to the active company."""
    if _require_auth(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    q            = request.GET.get("q", "").strip()
    warehouse_id = request.GET.get("warehouse", "").strip()
    supplier_id  = request.GET.get("supplier", "").strip()
    company_id   = _get_company_id(request)
    store_id     = _get_store_id(request)

    supplier_relations = ProductSupplier.objects.filter(active=True).select_related("supplier")
    if company_id:
        supplier_relations = supplier_relations.filter(company_id=company_id)
    if supplier_id:
        supplier_relations = supplier_relations.filter(supplier_id=supplier_id)
    qs = Product.objects.filter(active=True).select_related("unit").prefetch_related(
        "unit_conversions__unit",
        Prefetch("supplier_relations", queryset=supplier_relations, to_attr="matched_supplier_relations"),
    )
    if company_id:
        qs = qs.filter(company_id=company_id)
    if q:
        product_fields = (
            Q(name__icontains=q) | Q(sku__icontains=q)
            | Q(barcode__icontains=q) | Q(model__icontains=q)
        )
        supplier_matches = ProductSupplier.objects.filter(
            product_id=OuterRef("pk"), active=True,
        ).filter(
            Q(supplier_code__icontains=q)
            | Q(supplier_product_name__icontains=q)
        )
        if supplier_id:
            supplier_matches = supplier_matches.filter(supplier_id=supplier_id)
        qs = qs.annotate(
            matches_supplier_catalog=Exists(supplier_matches)
        ).filter(product_fields | Q(matches_supplier_catalog=True))
        qs = qs.distinct()
        products = list(qs.order_by("name")[:50])
    else:
        products = list(qs.order_by("-created_at")[:50])

    # Build stock map for this warehouse in a single query
    stock_map: dict[str, float] = {}
    if warehouse_id and products:
        for s in StockByWarehouse.objects.filter(
            product_id__in=[p.pk for p in products],
            warehouse_id=warehouse_id,
        ):
            stock_map[str(s.product_id)] = float(s.quantity)

    total_stock_map: dict[str, float] = {}
    if products:
        total_stock_qs = StockByWarehouse.objects.filter(
            product_id__in=[p.pk for p in products],
        )
        if store_id:
            total_stock_qs = total_stock_qs.filter(warehouse__store_id=store_id)

        for s in total_stock_qs.values('product_id').annotate(total=Sum('quantity')):
            total_stock_map[str(s['product_id'])] = float(s['total'])

    return JsonResponse({
        "products": [
            {
                "id":             str(p.pk),
                "name":           p.name,
                "sku":            p.sku or "",
                "unit":           p.unit.code if p.unit else "",
                "unit_id":        str(p.unit_id) if p.unit_id else "",
                "units": [
                    {"id": str(c.unit_id), "code": c.unit.code, "name": c.unit.name,
                     "factor": float(c.conversion_factor),
                     "sale_price": float(c.sale_price) if c.sale_price is not None else None,
                     "purchase_price": float(c.purchase_price) if c.purchase_price is not None else None}
                    for c in p.unit_conversions.all() if c.active
                ] or [{"id": str(p.unit_id), "code": p.unit.code, "name": p.unit.name,
                       "factor": 1, "sale_price": None, "purchase_price": None}],
                "price_purchase": float(p.price_purchase or 0),
                "supplier_code": p.matched_supplier_relations[0].supplier_code if p.matched_supplier_relations else "",
                "supplier_product_name": p.matched_supplier_relations[0].supplier_product_name if p.matched_supplier_relations else "",
                "supplier_purchase_price": float(p.matched_supplier_relations[0].purchase_price) if p.matched_supplier_relations and p.matched_supplier_relations[0].purchase_price is not None else None,
                "price_sale":     float(p.price_sale or 0),
                "stock":          stock_map.get(str(p.pk), 0),
                "total_stock":    total_stock_map.get(str(p.pk), 0),
            }
            for p in products
        ]
    })


# ── Product stock (single lookup) ─────────────────────────────────────────────

@require_GET
def product_stock(request):
    """Return stock for a single product at a given warehouse."""
    if _require_auth(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    product_id   = request.GET.get("product", "").strip()
    warehouse_id = request.GET.get("warehouse", "").strip()

    if not product_id or not warehouse_id:
        return JsonResponse({"stock": 0})

    try:
        s = StockByWarehouse.objects.get(product_id=product_id, warehouse_id=warehouse_id)
        return JsonResponse({"stock": float(s.quantity)})
    except StockByWarehouse.DoesNotExist:
        return JsonResponse({"stock": 0})


@require_GET
def product_stock_by_warehouse(request):
    """Stock base de un producto en todos los almacenes de la empresa activa."""
    if _require_auth(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    product_id = request.GET.get("product", "").strip()
    company_id = _get_company_id(request)
    if not product_id or not company_id:
        return JsonResponse({"error": "Producto y empresa activa son requeridos."}, status=400)

    product = Product.objects.filter(
        pk=product_id, company_id=company_id, active=True
    ).select_related("unit").first()
    if product is None:
        return JsonResponse({"error": "Producto no encontrado."}, status=404)

    warehouses = list(
        Warehouse.objects.filter(store__company_id=company_id, active=True)
        .select_related("store")
        .order_by("store__name", "name")
    )
    stock_map = {
        str(stock.warehouse_id): stock.quantity
        for stock in StockByWarehouse.objects.filter(
            product=product, warehouse_id__in=[warehouse.pk for warehouse in warehouses]
        )
    }
    return JsonResponse({
        "product": {
            "id": str(product.pk),
            "name": product.name,
            "sku": product.sku or "",
            "unit_code": product.unit.code,
            "unit_name": product.unit.name,
        },
        "warehouses": [
            {
                "id": str(warehouse.pk),
                "store": warehouse.store.name,
                "warehouse": warehouse.name,
                "stock": str(stock_map.get(str(warehouse.pk), 0)),
            }
            for warehouse in warehouses
        ],
    })


# ── Supplier search ───────────────────────────────────────────────────────────
@require_GET
def supplier_search(request):
    """Return up to 30 active suppliers matching `q` (name or document_number)."""
    if _require_auth(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    q = request.GET.get("q", "").strip()
    company_id = _get_company_id(request)
    qs = Supplier.objects.filter(active=True)
    if company_id:
        qs = qs.filter(company_id=company_id)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(document_number__icontains=q))
    qs = qs.order_by("name")[:50]

    return JsonResponse({
        "results": [
            {
                "id": str(s.pk),
                "text": f"{s.document_number} — {s.name}",
                "name": s.name,
                "document_number": s.document_number,
            }
            for s in qs
        ]
    })


# ── Customer search ───────────────────────────────────────────────────────────
@require_GET
def customer_search(request):
    """Return up to 30 active customers matching `q` (legal_name, trade_name or document_number)."""
    if _require_auth(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    q = request.GET.get("q", "").strip()
    company_id = _get_company_id(request)
    qs = Customer.objects.filter(active=True)
    if company_id:
        qs = qs.filter(company_id=company_id)
    if q:
        qs = qs.filter(
            Q(legal_name__icontains=q)
            | Q(trade_name__icontains=q)
            | Q(document_number__icontains=q)
        )
    qs = qs.order_by("legal_name")[:50]

    return JsonResponse({
        "results": [
            {
                "id": str(c.pk),
                "text": f"{c.document_number} — {c.legal_name}",
                "document_number": c.document_number,
                "legal_name": c.legal_name,
                "trade_name": c.trade_name or "",
                "address": c.address or "",
            }
            for c in qs
        ]
    })


# ── Quick create product ───────────────────────────────────────────────────────
@require_http_methods(["POST"])
def product_quick_create(request):
    """Create a product with minimal data and return its JSON representation."""
    if _require_auth(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Datos inválidos."}, status=400)

    name    = (data.get("name")    or "").strip()
    sku     = (data.get("sku")     or "").strip()
    unit_id = (data.get("unit_id") or "").strip()

    if not name:
        return JsonResponse({"error": "El nombre del producto es requerido."}, status=400)
    if not unit_id:
        return JsonResponse({"error": "La unidad de medida es requerida."}, status=400)

    try:
        unit = Unit.objects.get(pk=unit_id)
    except (Unit.DoesNotExist, Exception):
        return JsonResponse({"error": "Unidad no encontrada."}, status=400)

    if not sku:
        sku = "P-" + str(uuid_lib.uuid4())[:8].upper()

    company_id = _get_company_id(request)

    try:
        with transaction.atomic():
            product = Product.objects.create(
                name=name,
                sku=sku,
                unit=unit,
                active=True,
                company_id=company_id or None,
            )
            ProductUnit.objects.create(
                product=product,
                unit=unit,
                conversion_factor=1,
                is_default_sale=True,
                is_default_purchase=True,
                active=True,
            )
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(
        {
            "id":             str(product.pk),
            "name":           product.name,
            "sku":            product.sku,
            "unit":           product.unit.code if product.unit else "",
            "unit_id":        str(product.unit_id) if product.unit_id else "",
            "units": [{
                "id": str(product.unit_id),
                "code": product.unit.code,
                "name": product.unit.name,
                "factor": 1,
                "sale_price": None,
                "purchase_price": None,
            }],
            "price_purchase": float(product.price_purchase or 0),
            "price_sale":     float(product.price_sale or 0),
        },
        status=201,
    )

# ── Price list prices ────────────────────────────────────────────────────────
@require_GET
def price_list_prices(request, pk):
    """Return prices for given product IDs in a price list."""
    if _require_auth(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    product_ids = [
        pid.strip() for pid in request.GET.get("products", "").split(",")
        if pid.strip()
    ]

    prices = ProductPrice.objects.filter(
        price_list_id=pk,
        active=True,
    )
    if product_ids:
        prices = prices.filter(product_id__in=product_ids)

    return JsonResponse({
        "prices": {
            str(pp.product_id): float(pp.amount)
            for pp in prices
        }
    })

# ── Category search ──────────────────────────────────────────────────────────
@require_GET
def category_search(request):
    if _require_auth(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    query = request.GET.get("q", "").strip()
    company_id = _get_company_id(request)
    qs = Category.objects.filter(active=True)
    if company_id:
        qs = qs.filter(company_id=company_id)
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(code__icontains=query))
    return JsonResponse({"results": [{"id": str(c.pk), "text": c.name} for c in qs.order_by("name")[:50]]})

# ── Brand search ──────────────────────────────────────────────────────────────
@require_GET
def brand_search(request):
    if _require_auth(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    query = request.GET.get("q", "").strip()
    company_id = _get_company_id(request)
    qs = Brand.objects.filter(active=True)
    if company_id:
        qs = qs.filter(company_id=company_id)
    if query:
        qs = qs.filter(name__icontains=query)
    return JsonResponse({"results": [{"id": str(b.pk), "text": b.name} for b in qs.order_by("name")[:50]]})

# ── Location search ───────────────────────────────────────────────────────────
@require_GET
def location_search(request):
    """Return active warehouse locations for a given warehouse."""
    if _require_auth(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    warehouse_id = request.GET.get("warehouse", "").strip()
    q = request.GET.get("q", "").strip()

    qs = WarehouseLocation.objects.filter(active=True)
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    qs = qs.order_by("code")[:100]

    return JsonResponse({
        "results": [
            {
                "id": str(loc.pk),
                "text": f"{loc.code} — {loc.name}",
                "code": loc.code,
                "name": loc.name,
            }
            for loc in qs
        ]
    })
