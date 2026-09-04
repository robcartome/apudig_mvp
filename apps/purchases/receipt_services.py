from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.models import AuditLog
from apps.inventory.models import MovementOrigin
from apps.inventory.services import confirm_movement, register_entry, register_exit

from .models import (
    PurchaseOrder, PurchaseOrderStatus, PurchaseReceipt, PurchaseReceiptLine,
    PurchaseReceiptStatus,
)


def received_quantities(order):
    rows = PurchaseReceiptLine.objects.filter(
        purchase_order_line__purchase_order=order,
        purchase_receipt__status=PurchaseReceiptStatus.REGISTERED,
    ).values("purchase_order_line_id").annotate(total=Sum("quantity"))
    return {row["purchase_order_line_id"]: row["total"] for row in rows}


def _audit(receipt, action, user=None):
    AuditLog.objects.create(
        user=user, action=action, entity="PurchaseReceipt", entity_id=str(receipt.pk),
        meta_data={
            "purchase_order_id": str(receipt.purchase_order_id),
            "receipt_number": receipt.receipt_number, "status": receipt.status,
        },
    )


@transaction.atomic
def register_purchase_receipt(*, order_id, company_id, warehouse, receipt_number, receipt_date, lines, created_by=None, notes=""):
    order = PurchaseOrder.objects.select_for_update().select_related("store", "supplier").get(
        pk=order_id, company_id=company_id
    )
    if order.status not in (PurchaseOrderStatus.APPROVED, PurchaseOrderStatus.CLOSED):
        raise ValueError("La orden debe estar aprobada para registrar una recepcion.")
    if str(warehouse.store_id) != str(order.store_id):
        raise ValueError("El almacen debe pertenecer a la sucursal de la orden.")

    order_lines = {
        line.pk: line for line in order.lines.select_for_update().select_related("product", "unit")
    }
    already_received = received_quantities(order)
    normalized = []
    seen = set()
    for raw in lines:
        line_id = getattr(raw.get("purchase_order_line"), "pk", raw.get("purchase_order_line"))
        if line_id in seen or line_id not in order_lines:
            raise ValueError("La linea de recepcion no pertenece a la orden o esta duplicada.")
        seen.add(line_id)
        order_line = order_lines[line_id]
        if not order_line.product_id or not order_line.product.tracks_inventory:
            raise ValueError("Solo se pueden recibir fisicamente productos inventariables.")
        quantity = Decimal(str(raw.get("quantity") or 0))
        pending = Decimal(str(order_line.quantity)) - Decimal(str(already_received.get(line_id, 0)))
        if quantity <= 0:
            continue
        if quantity > pending:
            raise ValueError(f"La cantidad recibida de {order_line.description} supera el pendiente ({pending}).")
        normalized.append((order_line, quantity))
    if not normalized:
        raise ValueError("Ingresa al menos una cantidad a recibir.")

    receipt = PurchaseReceipt.objects.create(
        purchase_order=order, warehouse=warehouse,
        receipt_number=receipt_number.strip().upper(), receipt_date=receipt_date,
        notes=notes, created_by=created_by,
    )
    for order_line, quantity in normalized:
        PurchaseReceiptLine.objects.create(
            purchase_receipt=receipt, purchase_order_line=order_line, quantity=quantity
        )

    movement = register_entry(
        store_id=str(order.store_id), warehouse_id=str(warehouse.pk), date=receipt_date,
        lines=[{
            "product_id": line.product_id, "quantity": quantity,
            "unit_id": line.unit_id, "unit_price": line.unit_price,
        } for line, quantity in normalized],
        created_by=created_by, origin=MovementOrigin.PURCHASE,
        purchase_receipt=receipt, supplier=order.supplier,
        series="OC", number=receipt.receipt_number[:20], reference_doc=str(order.pk),
        reason="Recepcion de orden de compra",
        description=f"Recepcion {receipt.receipt_number} de {order.order_number}",
    )
    confirm_movement(movement, confirmed_by=created_by)

    received_after = received_quantities(order)
    receivable = [line for line in order_lines.values() if line.product_id and line.product.tracks_inventory]
    if receivable and all(Decimal(str(received_after.get(line.pk, 0))) >= line.quantity for line in receivable):
        order.status = PurchaseOrderStatus.CLOSED
        order.save(update_fields=("status", "updated_at"))
    elif order.status == PurchaseOrderStatus.CLOSED:
        order.status = PurchaseOrderStatus.APPROVED
        order.save(update_fields=("status", "updated_at"))
    _audit(receipt, "REGISTER", created_by)
    return receipt


@transaction.atomic
def cancel_purchase_receipt(receipt_id, *, company_id, cancelled_by=None):
    receipt = PurchaseReceipt.objects.select_for_update().select_related(
        "purchase_order", "warehouse", "purchase_order__supplier"
    ).get(pk=receipt_id, purchase_order__company_id=company_id)
    if receipt.status == PurchaseReceiptStatus.CANCELLED:
        return receipt
    for original in receipt.inventory_movements.select_for_update().filter(
        origin=MovementOrigin.PURCHASE, reversal_of__isnull=True
    ).prefetch_related("details"):
        reversal = register_exit(
            store_id=str(original.store_id), warehouse_id=str(original.warehouse_id),
            date=timezone.now(),
            lines=[{
                "product_id": detail.product_id, "quantity": detail.quantity,
                "unit_id": detail.unit_id, "unit_price": detail.unit_price,
            } for detail in original.details.all()],
            created_by=cancelled_by, origin=MovementOrigin.PURCHASE_REVERSAL,
            purchase_receipt=receipt, reversal_of=original,
            supplier=receipt.purchase_order.supplier,
            series="OC", number=receipt.receipt_number[:20], reference_doc=str(receipt.purchase_order_id),
            reason="Cancelacion de recepcion de compra",
            description=f"Reversion de recepcion {receipt.receipt_number}",
        )
        confirm_movement(reversal, confirmed_by=cancelled_by)
    receipt.status = PurchaseReceiptStatus.CANCELLED
    receipt.save(update_fields=("status", "updated_at"))
    order = receipt.purchase_order
    if order.status == PurchaseOrderStatus.CLOSED:
        order.status = PurchaseOrderStatus.APPROVED
        order.save(update_fields=("status", "updated_at"))
    _audit(receipt, "CANCEL", cancelled_by)
    return receipt
