from collections import defaultdict, deque
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.inventory.models import ProductSupplier

from .models import (
    LandedCostStatus, PurchaseDocument, PurchaseDocumentLine, PurchaseDocumentStatus,
    PurchaseLandedCostAllocation, PurchaseOrderLine, PurchaseReceiptLine,
    PurchaseReceiptStatus, SupplierPaymentAllocation, SupplierPaymentStatus,
)


def search_purchase_documents(
    company_id, store_id=None, query=None, status=None, *, date_from=None,
    date_to=None, created_from=None, created_to=None, number=None, series=None,
    supplier=None, payment_status=None, total_min=None, total_max=None,
):
    qs = PurchaseDocument.objects.for_company(company_id).select_related(
        "store", "supplier", "document_type", "payment_method"
    ).prefetch_related("lines__product", "lines__receipt_matches").annotate(
        paid_amount=Coalesce(
            Sum(
                "installments__payment_allocations__amount",
                filter=Q(installments__payment_allocations__payment__status="REGISTERED"),
            ),
            Value(Decimal("0")),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
        last_payment_date=Max(
            "installments__payment_allocations__payment__payment_date",
            filter=Q(installments__payment_allocations__payment__status="REGISTERED"),
        ),
    ).annotate(
        payment_balance=ExpressionWrapper(
            F("total") - F("paid_amount"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )
    if store_id:
        qs = qs.filter(store_id=store_id)
    if query:
        qs = qs.filter(
            Q(supplier_name__icontains=query)
            | Q(supplier_document_number__icontains=query)
            | Q(series__icontains=query)
            | Q(number__icontains=query)
        )
    if status:
        qs = qs.filter(document_status=status)
    if date_from:
        qs = qs.filter(issue_date__gte=date_from)
    if date_to:
        qs = qs.filter(issue_date__lte=date_to)
    if created_from:
        qs = qs.filter(created_at__date__gte=created_from)
    if created_to:
        qs = qs.filter(created_at__date__lte=created_to)
    if number:
        qs = qs.filter(number__icontains=number)
    if series:
        qs = qs.filter(series__icontains=series)
    if supplier:
        qs = qs.filter(
            Q(supplier_name__icontains=supplier)
            | Q(supplier_document_number__icontains=supplier)
        )
    if payment_status:
        qs = qs.filter(payment_status=payment_status)
    if total_min is not None:
        qs = qs.filter(total__gte=total_min)
    if total_max is not None:
        qs = qs.filter(total__lte=total_max)
    return qs.order_by("-issue_date", "-created_at")


def get_purchase_document(company_id, store_id, pk):
    return (
        PurchaseDocument.objects.for_company(company_id)
        .filter(store_id=store_id)
        .select_related("store", "supplier", "document_type", "created_by", "warehouse", "payment_method")
        .prefetch_related(
            "lines__product", "lines__unit", "lines__receipt_matches__movement_detail__movement",
            "inventory_movements",
        )
        .get(pk=pk)
    )


def get_purchase_price_history(
    company_id, store_id=None, *, product_id=None, supplier_id=None,
    date_from=None, date_to=None,
):
    """Return registered invoiced prices and their historical comparisons."""
    qs = (
        PurchaseDocumentLine.objects
        .filter(
            purchase_document__company_id=company_id,
            purchase_document__document_status=PurchaseDocumentStatus.REGISTERED,
            product__isnull=False,
        )
        .select_related("purchase_document__supplier", "product", "unit")
        .order_by("purchase_document__issue_date", "purchase_document__created_at", "position")
    )
    if store_id:
        qs = qs.filter(purchase_document__store_id=store_id)
    if product_id:
        qs = qs.filter(product_id=product_id)
    if supplier_id:
        qs = qs.filter(purchase_document__supplier_id=supplier_id)
    if date_from:
        qs = qs.filter(purchase_document__issue_date__gte=date_from)
    if date_to:
        qs = qs.filter(purchase_document__issue_date__lte=date_to)

    lines = list(qs)
    relation_prices = {
        (relation.product_id, relation.supplier_id): relation.purchase_price
        for relation in ProductSupplier.objects.filter(
            company_id=company_id,
            product_id__in={line.product_id for line in lines},
            supplier_id__in={line.purchase_document.supplier_id for line in lines},
            active=True,
        )
    }
    previous_by_product_supplier = {}
    rows = []
    for line in lines:
        key = (line.product_id, line.purchase_document.supplier_id)
        currency_factor = line.purchase_document.exchange_rate if line.purchase_document.currency != "PEN" else 1
        base_invoiced_price = line.price_unit * currency_factor / line.conversion_factor
        previous = previous_by_product_supplier.get(key)
        variance = base_invoiced_price - previous if previous is not None else None
        variance_percent = variance * 100 / previous if variance is not None and previous else None
        rows.append({
            "line": line,
            "document": line.purchase_document,
            "product": line.product,
            "supplier": line.purchase_document.supplier,
            "invoiced_price": line.price_unit,
            "base_invoiced_price": base_invoiced_price,
            "previous_price": previous,
            "variance": variance,
            "variance_percent": variance_percent,
            "current_product_price": line.product.price_purchase,
            "current_supplier_price": relation_prices.get(key),
        })
        previous_by_product_supplier[key] = base_invoiced_price
    rows.reverse()
    return rows


def get_purchase_price_comparison(
    company_id, store_id=None, *, product_id=None, supplier_id=None,
    date_from=None, date_to=None, price_decimal_places=2, price_count=5,
):
    """Return the latest effective unit-price changes per product and supplier.

    Prices use ``PurchaseDocumentLine.price_unit`` (IGV included when taxable),
    converted to PEN and the product base unit. Global document discounts are
    deliberately not part of this comparison.

    The queryset is streamed and each group retains at most ``price_count``
    events, so memory and rendered output no longer grow with every invoice.
    Rows before ``date_from`` are still read as a baseline, which lets the first
    price inside the selected period be compared correctly.
    """
    price_count = max(1, min(int(price_count), 5))
    quantizer = Decimal("1").scaleb(-price_decimal_places)
    qs = (
        PurchaseDocumentLine.objects
        .filter(
            purchase_document__company_id=company_id,
            purchase_document__document_status=PurchaseDocumentStatus.REGISTERED,
            product__isnull=False,
        )
        .select_related("purchase_document__supplier", "product")
        .only(
            "id", "position", "product_id", "unit_price", "tax_type", "igv_rate",
            "conversion_factor", "purchase_document_id", "product__id", "product__sku",
            "product__name", "purchase_document__id", "purchase_document__issue_date",
            "purchase_document__created_at", "purchase_document__currency",
            "purchase_document__exchange_rate", "purchase_document__supplier_id",
            "purchase_document__series", "purchase_document__number",
            "purchase_document__supplier__id", "purchase_document__supplier__name",
        )
        .order_by(
            "purchase_document__issue_date",
            "purchase_document__created_at",
            "position",
            "pk",
        )
    )
    if store_id:
        qs = qs.filter(purchase_document__store_id=store_id)
    if product_id:
        qs = qs.filter(product_id=product_id)
    if supplier_id:
        qs = qs.filter(purchase_document__supplier_id=supplier_id)
    if date_to:
        qs = qs.filter(purchase_document__issue_date__lte=date_to)

    previous_by_group = {}
    groups = {}
    for line in qs.iterator(chunk_size=2000):
        document = line.purchase_document
        key = (line.product_id, document.supplier_id)
        currency_factor = document.exchange_rate if document.currency != "PEN" else Decimal("1")
        base_price = line.price_unit * currency_factor / line.conversion_factor
        comparable_price = base_price.quantize(quantizer)
        previous_price = previous_by_group.get(key)
        changed = previous_price is None or comparable_price != previous_price
        previous_by_group[key] = comparable_price

        if not changed or (date_from and document.issue_date < date_from):
            continue

        group = groups.setdefault(key, {
            "product": line.product,
            "supplier": document.supplier,
            "events": deque(maxlen=price_count),
        })
        variance = comparable_price - previous_price if previous_price is not None else None
        variance_percent = (
            variance * Decimal("100") / previous_price
            if variance is not None and previous_price else None
        )
        group["events"].append({
            "document": document,
            "price": comparable_price,
            "previous_price": previous_price,
            "variance": variance,
            "variance_percent": variance_percent,
        })

    rows = []
    for key, group in groups.items():
        prices = list(reversed(group["events"]))
        latest = prices[0]
        prices.extend([None] * (price_count - len(prices)))
        rows.append({
            "product": group["product"],
            "supplier": group["supplier"],
            "prices": prices,
            "latest_variance": latest["variance"],
            "latest_variance_percent": latest["variance_percent"],
        })

    return sorted(
        rows,
        key=lambda row: (
            row["product"].sku.casefold(),
            row["product"].name.casefold(),
            row["supplier"].name.casefold(),
        ),
    )


def get_purchase_analytics(company_id, store_id, *, date_from=None, date_to=None, supplier_id=None):
    """Cross-domain purchasing indicators, always scoped to one company and store."""
    documents = PurchaseDocument.objects.filter(
        company_id=company_id, store_id=store_id,
        document_status=PurchaseDocumentStatus.REGISTERED,
    ).select_related("supplier", "document_type")
    if date_from:
        documents = documents.filter(issue_date__gte=date_from)
    if date_to:
        documents = documents.filter(issue_date__lte=date_to)
    if supplier_id:
        documents = documents.filter(supplier_id=supplier_id)
    documents = list(documents)
    document_ids = [document.pk for document in documents]

    paid_by_document = {
        row["installment__purchase_document_id"]: row["total"]
        for row in SupplierPaymentAllocation.objects.filter(
            installment__purchase_document_id__in=document_ids,
            payment__status=SupplierPaymentStatus.REGISTERED,
        ).values("installment__purchase_document_id").annotate(total=Sum("amount"))
    }
    landed_by_document = {
        row["purchase_document_line__purchase_document_id"]: row["total"]
        for row in PurchaseLandedCostAllocation.objects.filter(
            purchase_document_line__purchase_document_id__in=document_ids,
            landed_cost__status=LandedCostStatus.ALLOCATED,
        ).values("purchase_document_line__purchase_document_id").annotate(total=Sum("amount"))
    }

    supplier_rows = defaultdict(lambda: {
        "supplier": None, "document_count": 0, "spend_pen": Decimal("0"),
        "paid_pen": Decimal("0"), "balance_pen": Decimal("0"), "landed_cost_pen": Decimal("0"),
    })
    total_spend_pen = total_paid_pen = total_balance_pen = total_landed_pen = Decimal("0")
    aging = {"current": Decimal("0"), "days_1_30": Decimal("0"), "days_31_60": Decimal("0"), "days_61_plus": Decimal("0")}
    today = timezone.localdate()
    for document in documents:
        factor = document.exchange_rate if document.currency != "PEN" else Decimal("1")
        paid = paid_by_document.get(document.pk, Decimal("0"))
        balance = max(document.total - paid, Decimal("0"))
        landed = landed_by_document.get(document.pk, Decimal("0"))
        spend_pen, paid_pen = document.total * factor, paid * factor
        balance_pen, landed_pen = balance * factor, landed * factor
        total_spend_pen += spend_pen
        total_paid_pen += paid_pen
        total_balance_pen += balance_pen
        total_landed_pen += landed_pen
        row = supplier_rows[document.supplier_id]
        row["supplier"] = document.supplier
        row["document_count"] += 1
        row["spend_pen"] += spend_pen
        row["paid_pen"] += paid_pen
        row["balance_pen"] += balance_pen
        row["landed_cost_pen"] += landed_pen
        if balance_pen > 0:
            overdue_days = (today - (document.due_date or document.issue_date)).days
            bucket = "current" if overdue_days <= 0 else "days_1_30" if overdue_days <= 30 else "days_31_60" if overdue_days <= 60 else "days_61_plus"
            aging[bucket] += balance_pen

    order_lines = PurchaseOrderLine.objects.filter(
        purchase_order__company_id=company_id, purchase_order__store_id=store_id,
        product__isnull=False, product__tracks_inventory=True,
    ).select_related("purchase_order", "product")
    if date_from:
        order_lines = order_lines.filter(purchase_order__order_date__gte=date_from)
    if date_to:
        order_lines = order_lines.filter(purchase_order__order_date__lte=date_to)
    if supplier_id:
        order_lines = order_lines.filter(purchase_order__supplier_id=supplier_id)
    order_lines = list(order_lines)
    order_line_ids = [line.pk for line in order_lines]
    received = {
        row["purchase_order_line_id"]: row["total"]
        for row in PurchaseReceiptLine.objects.filter(
            purchase_order_line_id__in=order_line_ids,
            purchase_receipt__status=PurchaseReceiptStatus.REGISTERED,
        ).values("purchase_order_line_id").annotate(total=Sum("quantity"))
    }
    invoiced = {
        row["purchase_order_line_id"]: row["total"]
        for row in PurchaseDocumentLine.objects.filter(
            purchase_order_line_id__in=order_line_ids,
            purchase_document__document_status=PurchaseDocumentStatus.REGISTERED,
        ).values("purchase_order_line_id").annotate(total=Sum("quantity"))
    }
    ordered_qty = sum((line.quantity for line in order_lines), Decimal("0"))
    received_qty = sum((received.get(line.pk, Decimal("0")) for line in order_lines), Decimal("0"))
    invoiced_qty = sum((invoiced.get(line.pk, Decimal("0")) for line in order_lines), Decimal("0"))
    fulfillment_rows = [{
        "order": line.purchase_order, "product": line.product,
        "ordered": line.quantity, "received": received.get(line.pk, Decimal("0")),
        "invoiced": invoiced.get(line.pk, Decimal("0")),
        "pending": max(line.quantity - received.get(line.pk, Decimal("0")), Decimal("0")),
    } for line in order_lines if received.get(line.pk, Decimal("0")) < line.quantity]

    price_rows = get_purchase_price_history(
        company_id, store_id, supplier_id=supplier_id,
        date_from=date_from, date_to=date_to,
    )
    price_increases = sorted(
        (row for row in price_rows if row["variance"] is not None and row["variance"] > 0),
        key=lambda row: row["variance_percent"] or Decimal("0"), reverse=True,
    )
    return {
        "kpis": {
            "document_count": len(documents), "spend_pen": total_spend_pen,
            "paid_pen": total_paid_pen, "balance_pen": total_balance_pen,
            "landed_cost_pen": total_landed_pen, "ordered_qty": ordered_qty,
            "received_qty": received_qty, "invoiced_qty": invoiced_qty,
            "receipt_rate": received_qty * 100 / ordered_qty if ordered_qty else Decimal("0"),
        },
        "supplier_rows": sorted(supplier_rows.values(), key=lambda row: row["spend_pen"], reverse=True),
        "aging": aging, "fulfillment_rows": fulfillment_rows,
        "price_increases": price_increases[:20], "documents": documents,
    }
