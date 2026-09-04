from collections import defaultdict
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


def search_purchase_documents(company_id, store_id=None, query=None, status=None):
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
        base_invoiced_price = line.unit_price * currency_factor / line.conversion_factor
        previous = previous_by_product_supplier.get(key)
        variance = base_invoiced_price - previous if previous is not None else None
        variance_percent = variance * 100 / previous if variance is not None and previous else None
        rows.append({
            "line": line,
            "document": line.purchase_document,
            "product": line.product,
            "supplier": line.purchase_document.supplier,
            "invoiced_price": line.unit_price,
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
