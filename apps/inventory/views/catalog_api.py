"""
inventory/views/catalog_api.py - Public JSON catalog endpoints for frontend integration.

Access levels
─────────────
  Anonymous (no token)   → price_purchase is NOT included in the response.
  Employee (Bearer JWT)  → price_purchase IS included; company scoped to token.
"""
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.inventory.models import Product, ProductPrice, StockByWarehouse
from apps.users.auth_api import decode_bearer


def _get_company_id(request):
    return getattr(request, "active_company_id", None) or request.session.get("active_company_id")


def _to_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@require_GET
def catalog_products(request):
    """
    Compatible with ad_frontend getCatalogProducts:
    GET /catalog/products?search=&brand=&category=&limit=&offset=
    """
    token_payload = decode_bearer(request)
    is_employee = token_payload is not None

    search = (request.GET.get("search") or "").strip()
    brand = (request.GET.get("brand") or "").strip()
    category = (request.GET.get("category") or "").strip()
    limit = _to_int(request.GET.get("limit"), 20)
    offset = _to_int(request.GET.get("offset"), 0)

    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    qs = Product.objects.filter(active=True).select_related("unit", "brand", "category")

    # Company scoping: employee token takes precedence over session
    company_id = (
        (token_payload or {}).get("company_id")
        or _get_company_id(request)
    )
    if company_id:
        qs = qs.filter(company_id=company_id)

    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(sku__icontains=search))
    if brand:
        qs = qs.filter(brand_id=brand)
    if category:
        qs = qs.filter(category_id=category)

    total = qs.count()
    products = list(qs.order_by("name")[offset : offset + limit])
    product_ids = [p.pk for p in products]

    stock_map = {
        str(row["product_id"]): float(row["stock"] or 0)
        for row in (
            StockByWarehouse.objects.filter(product_id__in=product_ids)
            .values("product_id")
            .annotate(stock=Sum("quantity"))
        )
    }

    results = []
    for p in products:
        item = {
            "id": str(p.pk),
            "name": p.name,
            "sku": p.sku or None,
            "unit": p.unit.code if p.unit else None,
            "brand": p.brand.name if p.brand else None,
            "category": p.category.name if p.category else None,
            "price_sale": str(p.price_sale) if p.price_sale is not None else None,
            "stock": stock_map.get(str(p.pk), 0),
            "image": p.image or None,
        }
        if is_employee:
            item["price_purchase"] = str(p.price_purchase) if p.price_purchase is not None else None
        results.append(item)

    return JsonResponse(
        {
            "total": total,
            "limit": limit,
            "offset": offset,
            "results": results,
        }
    )


@require_GET
def catalog_product_detail(request, product_id):
    """
    Compatible with ad_frontend getProductDetail:
    GET /catalog/products/<uuid>/detail
    """
    token_payload = decode_bearer(request)
    is_employee = token_payload is not None

    qs = Product.objects.filter(pk=product_id).select_related("unit", "brand", "category")

    company_id = (
        (token_payload or {}).get("company_id")
        or _get_company_id(request)
    )
    if company_id:
        qs = qs.filter(company_id=company_id)

    product = qs.first()
    if not product:
        return JsonResponse({"detail": "Producto no encontrado"}, status=404)

    stock_rows = list(
        StockByWarehouse.objects.filter(product_id=product.pk)
        .select_related("warehouse")
        .order_by("warehouse__name")
    )

    stock_total = float(sum((row.quantity or 0) for row in stock_rows))

    prices = list(
        ProductPrice.objects.filter(product_id=product.pk, active=True)
        .select_related("price_list")
        .order_by("price_list__name")
    )

    data = {
        "id": str(product.pk),
        "name": product.name,
        "sku": product.sku or None,
        "unit": product.unit.code if product.unit else None,
        "description": product.description or None,
        "image": product.image or None,
        "brand": product.brand.name if product.brand else None,
        "category": product.category.name if product.category else None,
        "price_sale": str(product.price_sale) if product.price_sale is not None else None,
        "price_list": [
            {
                "price_list_name": item.price_list.name if item.price_list else "",
                "amount": str(item.amount),
                "currency": item.currency,
            }
            for item in prices
            if item.price_list
        ],
        "stock_total": stock_total,
        "stock_by_warehouse": [
            {
                "warehouse_name": row.warehouse.name if row.warehouse else "",
                "location": row.location or None,
                "quantity": float(row.quantity or 0),
            }
            for row in stock_rows
        ],
    }

    # price_purchase only visible to authenticated employees
    if is_employee:
        data["price_purchase"] = str(product.price_purchase) if product.price_purchase is not None else None

    return JsonResponse(data)
