from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum

from apps.core.models import AuditLog
from apps.inventory.models import Product, StockByWarehouse
from apps.inventory.pricing import unit_value

from .models import (
    LandedCostAllocationMethod, LandedCostStatus, PurchaseDocument,
    PurchaseDocumentStatus, PurchaseLandedCost, PurchaseLandedCostAllocation,
)


MONEY = Decimal("0.01")


def _money(value):
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def document_landed_cost_summary(document):
    allocations = PurchaseLandedCostAllocation.objects.filter(
        purchase_document_line__purchase_document=document,
        landed_cost__status=LandedCostStatus.ALLOCATED,
    ).values("purchase_document_line_id").annotate(total=Sum("amount"))
    by_line = {row["purchase_document_line_id"]: row["total"] for row in allocations}
    total = sum(by_line.values(), Decimal("0"))
    return {"total": _money(total), "by_line": by_line}


def _automatic_allocations(lines, amount, method):
    weights = []
    for line in lines:
        weight = line.subtotal if method == LandedCostAllocationMethod.VALUE else line.stock_quantity
        weights.append(Decimal(str(weight)))
    total_weight = sum(weights, Decimal("0"))
    if total_weight <= 0:
        raise ValueError("No existe una base positiva para distribuir el cargo.")
    result = []
    allocated = Decimal("0")
    for index, (line, weight) in enumerate(zip(lines, weights)):
        line_amount = amount - allocated if index == len(lines) - 1 else _money(amount * weight / total_weight)
        result.append((line, line_amount))
        allocated += line_amount
    return result


def _apply_allocations_to_average_cost(document, allocations, direction=1):
    """Incorpora cargos en moneda base al promedio del stock actualmente disponible."""
    currency_factor = Decimal("1") if document.currency == "PEN" else Decimal(str(document.exchange_rate or 0))
    for line, allocated in allocations:
        current_stock = StockByWarehouse.objects.filter(
            product_id=line.product_id,
            warehouse__store__company_id=document.company_id,
        ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
        if current_stock <= 0:
            continue
        product = Product.objects.select_for_update().get(pk=line.product_id)
        delta = Decimal(str(allocated)) * currency_factor / current_stock
        product.inventory_unit_cost = unit_value(max(
            Decimal("0"), Decimal(str(product.inventory_unit_cost)) + delta * direction,
        ))
        product.save(update_fields=("inventory_unit_cost", "updated_at"))


@transaction.atomic
def allocate_landed_cost(*, document_id, company_id, description, amount,
                         allocation_method, manual_allocations=None,
                         reference="", notes="", created_by=None):
    document = PurchaseDocument.objects.select_for_update().get(pk=document_id, company_id=company_id)
    if document.document_status != PurchaseDocumentStatus.REGISTERED:
        raise ValueError("Solo se pueden distribuir cargos sobre documentos registrados.")
    amount = _money(amount)
    if amount <= 0:
        raise ValueError("El importe del cargo debe ser mayor que cero.")
    lines = list(document.lines.select_related("product").filter(
        product__isnull=False, product__tracks_inventory=True
    ).order_by("position"))
    if not lines:
        raise ValueError("El documento no tiene productos inventariables para distribuir el cargo.")

    if allocation_method == LandedCostAllocationMethod.MANUAL:
        values = {
            getattr(item.get("line"), "pk", item.get("line")): _money(item.get("amount") or 0)
            for item in (manual_allocations or [])
        }
        eligible_ids = {line.pk for line in lines}
        if set(values) - eligible_ids:
            raise ValueError("Una asignacion manual no pertenece al documento.")
        allocations = [(line, values.get(line.pk, Decimal("0"))) for line in lines]
        if _money(sum((value for _, value in allocations), Decimal("0"))) != amount:
            raise ValueError("La suma de asignaciones manuales debe ser igual al importe del cargo.")
    elif allocation_method in (LandedCostAllocationMethod.VALUE, LandedCostAllocationMethod.QUANTITY):
        allocations = _automatic_allocations(lines, amount, allocation_method)
    else:
        raise ValueError("Metodo de distribucion no soportado.")

    landed_cost = PurchaseLandedCost.objects.create(
        purchase_document=document, description=description.strip(), reference=reference,
        amount=amount, allocation_method=allocation_method, notes=notes, created_by=created_by,
    )
    PurchaseLandedCostAllocation.objects.bulk_create([
        PurchaseLandedCostAllocation(
            landed_cost=landed_cost, purchase_document_line=line, amount=line_amount
        ) for line, line_amount in allocations
    ])
    _apply_allocations_to_average_cost(document, allocations)
    AuditLog.objects.create(
        user=created_by, action="ALLOCATE", entity="PurchaseLandedCost",
        entity_id=str(landed_cost.pk),
        meta_data={"document_id": str(document.pk), "amount": str(amount), "method": allocation_method},
    )
    return landed_cost


@transaction.atomic
def cancel_landed_cost(landed_cost_id, *, company_id, cancelled_by=None):
    landed_cost = PurchaseLandedCost.objects.select_for_update().get(
        pk=landed_cost_id, purchase_document__company_id=company_id
    )
    if landed_cost.status == LandedCostStatus.CANCELLED:
        return landed_cost
    allocations = [
        (allocation.purchase_document_line, allocation.amount)
        for allocation in landed_cost.allocations.select_related("purchase_document_line__product")
    ]
    _apply_allocations_to_average_cost(landed_cost.purchase_document, allocations, direction=-1)
    landed_cost.status = LandedCostStatus.CANCELLED
    landed_cost.save(update_fields=("status", "updated_at"))
    AuditLog.objects.create(
        user=cancelled_by, action="CANCEL", entity="PurchaseLandedCost",
        entity_id=str(landed_cost.pk), meta_data={"document_id": str(landed_cost.purchase_document_id)},
    )
    return landed_cost
