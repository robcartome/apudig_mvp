"""
inventory/views/api.py — JSON API endpoints for inventory UI interactions.
"""
import json
import uuid as uuid_lib

from django.db.models import Q, Sum
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from apps.partners.models import CoreCustomer, Supplier

from ..models import Product, StockByWarehouse, Unit, WarehouseLocation


def _get_company_id(request):
    return getattr(request, "active_company_id", None) or request.session.get("active_company_id")


def _get_store_id(request):
    return getattr(request, "active_store_id", None) or request.session.get("active_store_id")


def _require_auth(request):
    return not request.user.is_authenticated


# ── Product search ─────────────────────────────────────────────────────────────

@require_GET
def product_search(request):
    """Return up to 50 products matching `q`, scoped to the active company."""
    if _require_auth(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    q            = request.GET.get("q", "").strip()
    warehouse_id = request.GET.get("warehouse", "").strip()
    company_id   = _get_company_id(request)

    qs = Product.objects.filter(active=True).select_related("unit")
    if company_id:
        qs = qs.filter(company_id=company_id)
    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(sku__icontains=q) | Q(barcode__icontains=q)
        )
        products = list(qs.order_by("name")[:50])
    else:
        # No query → return the 50 most recently created products
        products = list(qs.order_by("-created_at")[:50])

    # Build stock map for this warehouse in a single query
    stock_map: dict[str, float] = {}
    if warehouse_id and products:
        for s in StockByWarehouse.objects.filter(
            product_id__in=[p.pk for p in products],
            warehouse_id=warehouse_id,
        ):
            stock_map[str(s.product_id)] = float(s.quantity)

    # Build total stock map (all warehouses)
    total_stock_map: dict[str, float] = {}
    if products:
        for s in StockByWarehouse.objects.filter(
            product_id__in=[p.pk for p in products],
        ).values('product_id').annotate(total=Sum('quantity')):
            total_stock_map[str(s['product_id'])] = float(s['total'])

    return JsonResponse({
        "products": [
            {
                "id":             str(p.pk),
                "name":           p.name,
                "sku":            p.sku or "",
                "unit":           p.unit.code if p.unit else "",
                "unit_id":        str(p.unit_id) if p.unit_id else "",
                "price_purchase": float(p.price_purchase or 0),
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
    qs = CoreCustomer.objects.filter(active=True)
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
        product = Product.objects.create(
            name=name,
            sku=sku,
            unit=unit,
            active=True,
            company_id=company_id or None,
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
            "price_purchase": float(product.price_purchase or 0),
            "stock":          0,
        },
        status=201,
    )


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
