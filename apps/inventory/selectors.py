"""
inventory/selectors.py — Consultas de lectura de inventario.
"""
from decimal import Decimal

from django.db.models import Exists, OuterRef, Q, Sum
from django.utils import timezone

from .models import Brand, Category, Movement, MovementDetail, MovementType, PriceList, Product, ProductPrice, ProductSupplier, StockByWarehouse, StoreProductConfig, Unit, Warehouse


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


def search_products(query: str, company_id=None, active_only: bool = False, supplier_id=None):
    qs = get_products(company_id=company_id, active_only=active_only)
    if query:
        product_fields = (
            Q(name__icontains=query)
            | Q(sku__icontains=query)
            | Q(barcode__icontains=query)
            | Q(model__icontains=query)
        )
        supplier_matches = ProductSupplier.objects.filter(
            product_id=OuterRef("pk"), active=True,
        ).filter(
            Q(supplier_code__icontains=query)
            | Q(supplier_product_name__icontains=query)
        )
        if supplier_id:
            supplier_matches = supplier_matches.filter(supplier_id=supplier_id)
        qs = qs.annotate(
            matches_supplier_catalog=Exists(supplier_matches)
        ).filter(product_fields | Q(matches_supplier_catalog=True))
    return qs.distinct()


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
        .prefetch_related("details__product__unit", "details__unit")
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
        .prefetch_related("details__product__unit", "details__unit", "audit_logs__changed_by")
        .select_related("store", "warehouse", "warehouse_origin", "warehouse_dest",
                        "supplier", "customer", "carrier", "document_type", "created_by", "confirmed_by", "closed_by")
        .get(pk=pk)
    )


def get_stock_for_product(product_id, store_id: str):
    """Retorna la cantidad total en stock para un producto en una sucursal."""
    result = (
        StockByWarehouse.objects
        .filter(product_id=product_id, warehouse__store_id=store_id)
        .aggregate(total=Sum("quantity"))
    )
    return result["total"] or Decimal("0")


# ── Reporte: Stock por Almacén mejorado ───────────────────────────────────────

def get_stock_report_enhanced(store_id: str, warehouse_id: str = "", query: str = ""):
    """Stock con min_stock y estado, filtrable por almacén y búsqueda."""
    qs = (
        StockByWarehouse.objects
        .select_related("product__unit", "product__category", "warehouse")
        .filter(warehouse__store_id=store_id)
        .order_by("warehouse__name", "product__name")
    )
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)
    if query:
        qs = qs.filter(
            Q(product__name__icontains=query)
            | Q(product__sku__icontains=query)
            | Q(product__barcode__icontains=query)
        )

    # Fetch min_stock configs for this store
    config_map: dict = {}
    if store_id:
        for cfg in StoreProductConfig.objects.filter(store_id=store_id).values("product_id", "min_stock"):
            config_map[str(cfg["product_id"])] = cfg["min_stock"]

    rows = []
    for s in qs:
        min_stock = config_map.get(str(s.product_id), 0)
        valuation = s.quantity * s.product.price_purchase
        rows.append({
            "warehouse": s.warehouse.name,
            "sku": s.product.sku,
            "product": s.product.name,
            "category": s.product.category.name if s.product.category else "-",
            "unit": s.product.unit.code if s.product.unit else "-",
            "quantity": s.quantity,
            "min_stock": min_stock,
            "status": "BAJO" if s.quantity <= min_stock else "NORMAL",
            "price_purchase": s.product.price_purchase,
            "valuation": valuation,
        })
    return rows


# ── Reporte: Stock comparativo por almacén ────────────────────────────────────

def get_stock_comparative(store_id: str, warehouse_ids: list = None, query: str = ""):
    """
    Returns (warehouses, rows, summary) where each row has stock keyed by warehouse id.

    warehouses — list of Warehouse objects for the selected warehouses.
    rows       — list of dicts: {product_id, sku, product, category, unit,
                                  stocks: {wh_id: qty}, total_stock, price_purchase,
                                  price_sale, total_valuation}
    summary    — {by_warehouse: {wh_id: total}, grand_total, grand_valuation}
    """
    wh_qs = Warehouse.objects.filter(store_id=store_id, active=True).order_by("name")
    if warehouse_ids:
        wh_qs = wh_qs.filter(id__in=warehouse_ids)
    warehouses = list(wh_qs)
    wh_ids = [str(wh.id) for wh in warehouses]

    # Fetch stock records for selected warehouses
    sbw_qs = (
        StockByWarehouse.objects
        .select_related("product__unit", "product__category")
        .filter(warehouse__store_id=store_id)
    )
    if wh_ids:
        sbw_qs = sbw_qs.filter(warehouse_id__in=wh_ids)
    if query:
        sbw_qs = sbw_qs.filter(
            Q(product__name__icontains=query)
            | Q(product__sku__icontains=query)
            | Q(product__barcode__icontains=query)
        )

    # Build product map
    product_map: dict = {}
    for s in sbw_qs:
        pid = str(s.product_id)
        if pid not in product_map:
            product_map[pid] = {
                "product_id": pid,
                "sku": s.product.sku,
                "product": s.product.name,
                "category": s.product.category.name if s.product.category else "-",
                "unit": s.product.unit.code if s.product.unit else "-",
                "price_purchase": s.product.price_purchase,
                "price_sale": s.product.price_sale,
                "stocks": {},
            }
        product_map[pid]["stocks"][str(s.warehouse_id)] = s.quantity

    # Build rows
    rows = []
    for row in sorted(product_map.values(), key=lambda r: r["product"]):
        total_stock = sum(row["stocks"].get(wid, Decimal("0")) for wid in wh_ids) if wh_ids else sum(row["stocks"].values(), Decimal("0"))
        row["total_stock"] = total_stock
        row["total_valuation"] = total_stock * row["price_purchase"]
        rows.append(row)

    # Summary
    by_warehouse: dict = {}
    grand_total = Decimal("0")
    grand_valuation = Decimal("0")
    for row in rows:
        for wid in wh_ids:
            by_warehouse[wid] = by_warehouse.get(wid, Decimal("0")) + row["stocks"].get(wid, Decimal("0"))
        grand_total += row["total_stock"]
        grand_valuation += row["total_valuation"]

    summary = {"by_warehouse": by_warehouse, "grand_total": grand_total, "grand_valuation": grand_valuation}
    return warehouses, rows, summary


# ── Reporte: Kardex de inventario ─────────────────────────────────────────────

def get_kardex_report(
    store_id: str,
    warehouse_id: str,
    date_from,
    date_to,
    category_id: str = "",
    product_id: str = "",
    show_previous_balance: bool = True,
):
    """
    Returns a list of kardex_groups, each being a dict:
      {product_id, sku, product_name, category, unit, entries: [...]}

    Each entry:
      {date, type, document, reference, partner, ingreso, salida, saldo,
       unit_value, avg_cost, value_ingreso, value_salida, value_saldo, is_previous}
    """
    # --- Movements within the period ---
    movements_qs = (
        Movement.objects
        .filter(store_id=store_id, status__in=["CONFIRMED", "CLOSED"])
        .select_related("warehouse", "warehouse_origin", "warehouse_dest", "supplier", "customer", "document_type")
        .prefetch_related("details__product__unit", "details__product__category")
        .order_by("date", "created_at")
    )

    # Filter movements that affect the target warehouse
    movements_qs = movements_qs.filter(
        Q(warehouse_id=warehouse_id)
        | Q(warehouse_origin_id=warehouse_id)
        | Q(warehouse_dest_id=warehouse_id)
    )

    if date_from:
        movements_in_period = movements_qs.filter(date__date__gte=date_from, date__date__lte=date_to)
    else:
        movements_in_period = movements_qs

    if category_id:
        movements_in_period = movements_in_period.filter(details__product__category_id=category_id)
    if product_id:
        movements_in_period = movements_in_period.filter(details__product_id=product_id)

    # Gather distinct products in period
    detail_qs = (
        MovementDetail.objects
        .filter(movement__in=movements_in_period)
        .select_related("product__unit", "product__category")
        .distinct()
    )
    if category_id:
        detail_qs = detail_qs.filter(product__category_id=category_id)
    if product_id:
        detail_qs = detail_qs.filter(product_id=product_id)

    product_ids_in_period = list(
        detail_qs.values_list("product_id", flat=True).distinct()
    )

    # Build product info map
    products_in_period = {
        str(p.id): p
        for p in Product.objects.filter(id__in=product_ids_in_period).select_related("unit", "category")
    }

    kardex_groups = []
    for pid in product_ids_in_period:
        prod = products_in_period.get(str(pid))
        if not prod:
            continue

        entries = []
        running_balance = Decimal("0")
        running_value = Decimal("0")

        # Previous balance (movements before date_from)
        if show_previous_balance and date_from:
            prev_movements = movements_qs.filter(
                date__date__lt=date_from,
                details__product_id=pid,
            ).distinct()
            for mv in prev_movements:
                for d in mv.details.filter(product_id=pid):
                    delta = _kardex_delta(mv, d, warehouse_id)
                    running_balance += delta
                    running_value += delta * d.unit_price

        if show_previous_balance and date_from:
            entries.append({
                "date": None,
                "type": "",
                "document": "",
                "reference": "",
                "partner": "SALDO ANTERIOR",
                "ingreso": None,
                "salida": None,
                "saldo": running_balance,
                "unit_value": None,
                "avg_cost": running_value / running_balance if running_balance else Decimal("0"),
                "value_ingreso": None,
                "value_salida": None,
                "value_saldo": running_value,
                "is_previous": True,
            })

        # Period movements
        period_details = (
            MovementDetail.objects
            .filter(movement__in=movements_in_period, product_id=pid)
            .select_related("movement__warehouse", "movement__warehouse_origin",
                            "movement__warehouse_dest", "movement__supplier",
                            "movement__customer", "movement__document_type")
            .order_by("movement__date", "movement__created_at")
        )

        for d in period_details:
            mv = d.movement
            delta = _kardex_delta(mv, d, warehouse_id)
            if delta == 0:
                continue

            ingreso = delta if delta > 0 else None
            salida = abs(delta) if delta < 0 else None
            running_balance += delta
            value_change = delta * d.unit_price
            running_value += value_change
            value_ingreso = value_change if delta > 0 else None
            value_salida = abs(value_change) if delta < 0 else None
            avg_cost = running_value / running_balance if running_balance else Decimal("0")

            partner = ""
            if mv.supplier:
                partner = mv.supplier.name if hasattr(mv.supplier, "name") else str(mv.supplier)
            elif mv.customer:
                partner = mv.customer.name if hasattr(mv.customer, "name") else str(mv.customer)

            doc_type = mv.document_type.name if mv.document_type else mv.get_type_display()
            doc_number = f"{mv.series}-{mv.number}" if mv.series and mv.number else mv.number or mv.reference_doc or ""

            entries.append({
                "date": mv.date,
                "type": mv.get_type_display(),
                "document": doc_type,
                "reference": doc_number,
                "partner": partner,
                "ingreso": ingreso,
                "salida": salida,
                "saldo": running_balance,
                "unit_value": d.unit_price,
                "avg_cost": avg_cost,
                "value_ingreso": value_ingreso,
                "value_salida": value_salida,
                "value_saldo": running_value,
                "is_previous": False,
            })

        kardex_groups.append({
            "product_id": str(pid),
            "sku": prod.sku,
            "product_name": prod.name,
            "category": prod.category.name if prod.category else "-",
            "unit": prod.unit.code if prod.unit else "-",
            "entries": entries,
        })

    kardex_groups.sort(key=lambda g: g["product_name"])
    return kardex_groups


def _kardex_delta(movement, detail, warehouse_id: str) -> Decimal:
    """Returns +qty for inbound, -qty for outbound at the given warehouse."""
    t = movement.type
    wh = str(warehouse_id)
    if t == MovementType.ENTRY:
        return detail.quantity if str(movement.warehouse_id) == wh else Decimal("0")
    if t == MovementType.EXIT:
        return -detail.quantity if str(movement.warehouse_id) == wh else Decimal("0")
    if t == MovementType.TRANSFER:
        if str(movement.warehouse_dest_id) == wh:
            return detail.quantity
        if str(movement.warehouse_origin_id) == wh:
            return -detail.quantity
        return Decimal("0")
    if t == MovementType.ADJUSTMENT:
        return detail.quantity if str(movement.warehouse_id) == wh else Decimal("0")
    return Decimal("0")


# ── Reporte: Movimientos de almacén ───────────────────────────────────────────

def get_movement_traceability_report(
    store_id: str,
    warehouse_id: str = "",
    movement_type: str = "",
    date_from=None,
    date_to=None,
    product_ids: list[str] | None = None,
    search: str = "",
    limit: int | None = 5000,
):
    """
    Returns a traceability report grouped by product.

    Result format:
      {
        products: [
          {
            product_id, sku, product, category, unit,
            opening_balance, closing_balance, qty_in, qty_out, amount_total,
            entries: [...]
          }
        ],
        summary_by_type: [...],
        total_rows, total_quantity, total_amount
      }
    """
    qs = (
        MovementDetail.objects
        .select_related(
            "movement",
            "movement__warehouse",
            "movement__warehouse_origin",
            "movement__warehouse_dest",
            "movement__supplier",
            "movement__customer",
            "movement__document_type",
            "movement__created_by",
            "movement__sales_document",
            "movement__reversal_of__sales_document",
            "movement__purchase_document",
            "movement__reversal_of__purchase_document",
            "product__unit",
            "product__category",
        )
        .filter(movement__store_id=store_id, movement__status__in=["CONFIRMED", "CLOSED"])
        .order_by("-movement__date", "-movement__created_at", "-id")
    )

    if movement_type:
        qs = qs.filter(movement__type=movement_type)

    if warehouse_id:
        qs = qs.filter(
            Q(movement__warehouse_id=warehouse_id)
            | Q(movement__warehouse_origin_id=warehouse_id)
            | Q(movement__warehouse_dest_id=warehouse_id)
        )

    if date_from:
        qs = qs.filter(movement__date__date__gte=date_from)
    if date_to:
        qs = qs.filter(movement__date__date__lte=date_to)

    if product_ids:
        qs = qs.filter(product_id__in=product_ids)

    if search:
        qs = qs.filter(
            Q(product__name__icontains=search)
            | Q(product__sku__icontains=search)
            | Q(product__barcode__icontains=search)
            | Q(movement__reference_doc__icontains=search)
        )

    total_matched = qs.count()
    if limit and limit > 0:
        qs = qs[:limit]

    rows = []
    for d in qs:
        mv = d.movement
        movement_type_code = mv.type

        if warehouse_id:
            signed_quantity = _kardex_delta(mv, d, warehouse_id)
        else:
            signed_quantity = Decimal(str(d.quantity or 0))
            if movement_type_code == MovementType.EXIT:
                signed_quantity = -abs(signed_quantity)
            elif movement_type_code == MovementType.TRANSFER:
                signed_quantity = Decimal(str(d.quantity or 0))
            elif movement_type_code == MovementType.ADJUSTMENT:
                signed_quantity = Decimal(str(d.quantity or 0))

        quantity = Decimal(str(d.quantity or 0))
        amount = abs(quantity) * Decimal(str(d.unit_price or 0))

        if mv.type == MovementType.TRANSFER:
            if mv.warehouse_origin_id == d.movement.warehouse_origin_id and warehouse_id and str(mv.warehouse_origin_id) == str(warehouse_id):
                warehouse_label = f"{mv.warehouse_origin.name} → {mv.warehouse_dest.name}"
            elif warehouse_id and str(mv.warehouse_dest_id) == str(warehouse_id):
                warehouse_label = f"{mv.warehouse_origin.name} → {mv.warehouse_dest.name}"
            else:
                warehouse_label = f"{mv.warehouse_origin.name if mv.warehouse_origin else '-'} → {mv.warehouse_dest.name if mv.warehouse_dest else '-'}"
        else:
            warehouse_label = mv.warehouse.name if mv.warehouse else "-"

        partner_type = ""
        partner_id = ""
        if mv.supplier:
            partner = mv.supplier.name
            partner_type = "supplier"
            partner_id = str(mv.supplier_id)
        elif mv.customer:
            partner = mv.customer.legal_name
            partner_type = "customer"
            partner_id = str(mv.customer_id)
        else:
            partner = "-"

        document = "-"
        if mv.document_type or mv.series or mv.number:
            doc_type = mv.document_type.name if mv.document_type else "OTROS"
            document = f"{doc_type} {mv.series or '0000'}-{mv.number or '0'}".strip()
        elif mv.reference_doc:
            document = mv.reference_doc

        sales_document = getattr(mv, "sales_document", None)
        if sales_document is None and mv.reversal_of_id:
            sales_document = getattr(mv.reversal_of, "sales_document", None)
        purchase_document = mv.purchase_document
        if purchase_document is None and mv.reversal_of_id:
            purchase_document = mv.reversal_of.purchase_document

        rows.append({
            "movement_id": str(mv.pk),
            "movement_detail_id": str(d.pk),
            "operation_id": str(mv.pk),
            "operation_code": mv.number or str(mv.pk)[:8],
            "date": mv.date,
            "type": movement_type_code,
            "type_label": mv.get_type_display(),
            "origin": mv.origin,
            "origin_label": mv.get_origin_display(),
            "warehouse": warehouse_label,
            "partner": partner,
            "partner_type": partner_type,
            "partner_id": partner_id,
            "document": document,
            "reference_doc": mv.reference_doc or "-",
            "sales_document_id": str(sales_document.pk) if sales_document else "",
            "purchase_document_id": str(purchase_document.pk) if purchase_document else "",
            "created_by": str(mv.created_by) if mv.created_by else "Sistema",
            "product_id": str(d.product_id),
            "sku": d.product.sku,
            "product": d.product.name,
            "category": d.product.category.name if d.product.category else "-",
            "unit": d.product.unit.code if d.product.unit else "-",
            "quantity": quantity,
            "signed_quantity": signed_quantity,
            "unit_price": Decimal(str(d.unit_price or 0)),
            "amount": amount,
        })

    grouped: dict[str, dict] = {}
    summary_by_type: dict[str, dict] = {}
    total_quantity = Decimal("0")
    total_amount = Decimal("0")

    for row in rows:
        pid = row["product_id"]
        product_group = grouped.setdefault(pid, {
            "product_id": pid,
            "sku": row["sku"],
            "product": row["product"],
            "category": row["category"],
            "unit": row["unit"],
            "entries": [],
            "qty_in": Decimal("0"),
            "qty_out": Decimal("0"),
            "movement_count": 0,
            "opening_balance": Decimal("0"),
            "closing_balance": Decimal("0"),
            "amount_total": Decimal("0"),
        })

        product_group["entries"].append(row)
        product_group["movement_count"] += 1
        product_group["closing_balance"] += row["signed_quantity"]
        product_group["amount_total"] += row["amount"]
        if row["signed_quantity"] >= 0:
            product_group["qty_in"] += row["signed_quantity"]
        else:
            product_group["qty_out"] += abs(row["signed_quantity"])

        st = summary_by_type.setdefault(row["type"], {
            "type": row["type"],
            "type_label": row["type_label"],
            "movements": 0,
            "quantity_total": Decimal("0"),
            "amount_total": Decimal("0"),
        })
        st["movements"] += 1
        st["quantity_total"] += row["signed_quantity"]
        st["amount_total"] += row["amount"]

        total_quantity += row["signed_quantity"]
        total_amount += row["amount"]

    products = list(grouped.values())
    for product in products:
        product["entries"] = sorted(product["entries"], key=lambda r: (r["date"], r["movement_detail_id"]), reverse=True)

    summary = sorted(summary_by_type.values(), key=lambda item: item["type_label"])
    return {
        "products": products,
        "summary_by_type": summary,
        "total_rows": len(rows),
        "total_matched": total_matched,
        "truncated": bool(limit and total_matched > len(rows)),
        "limit": limit,
        "total_quantity": total_quantity,
        "total_amount": total_amount,
        "rows": rows,
    }

