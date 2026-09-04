from django.db import transaction

from apps.core.models import AuditLog

from .models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus
from .services import _calculate_line, _normalize_line, _totals


def _audit(order, action, user=None):
    AuditLog.objects.create(
        user=user, action=action, entity="PurchaseOrder", entity_id=str(order.pk),
        meta_data={
            "company_id": str(order.company_id), "store_id": str(order.store_id),
            "status": order.status, "order_number": order.order_number,
        },
    )


def _validate_scope(company_id, store, supplier, lines):
    if str(store.company_id) != str(company_id):
        raise ValueError("La sucursal no pertenece a la empresa activa.")
    if str(supplier.company_id) != str(company_id):
        raise ValueError("El proveedor no pertenece a la empresa activa.")
    if not lines:
        raise ValueError("La orden debe tener al menos una linea.")


def _replace_lines(order, lines, calculated):
    order.lines.all().delete()
    for position, (raw, calc) in enumerate(zip(lines, calculated), start=1):
        concept = raw["product"] or raw["purchase_category"]
        PurchaseOrderLine.objects.create(
            purchase_order=order, position=position,
            product=raw["product"], purchase_category=raw.get("purchase_category"),
            description=raw.get("description") or concept.name,
            quantity=raw["quantity"], unit=raw["unit"], unit_code=raw["unit_code"],
            conversion_factor=raw["conversion_factor"], unit_price=raw["unit_price"],
            discount_amount=raw.get("discount_amount") or 0,
            tax_type=raw.get("tax_type", "10"), igv_rate=raw.get("igv_rate") or 0,
            memo=raw.get("memo", ""), **calc,
        )


@transaction.atomic
def create_purchase_order(*, company_id, store, supplier, lines, created_by=None, **kwargs):
    _validate_scope(company_id, store, supplier, lines)
    normalized = [_normalize_line(line, company_id) for line in lines]
    calculated = [_calculate_line(line) for line in normalized]
    totals = _totals(normalized, calculated)
    order = PurchaseOrder.objects.create(
        company_id=company_id, store=store, supplier=supplier, created_by=created_by,
        subtotal=totals["subtotal"], igv_total=totals["igv_total"],
        total_discount=totals["total_discount"], total=totals["total"], **kwargs,
    )
    _replace_lines(order, normalized, calculated)
    _audit(order, "CREATE", created_by)
    return order


@transaction.atomic
def update_purchase_order(order_id, *, company_id, store, supplier, lines, updated_by=None, **kwargs):
    order = PurchaseOrder.objects.select_for_update().get(pk=order_id, company_id=company_id)
    if order.status != PurchaseOrderStatus.DRAFT:
        raise ValueError("Solo se pueden editar ordenes en borrador.")
    _validate_scope(company_id, store, supplier, lines)
    normalized = [_normalize_line(line, company_id) for line in lines]
    calculated = [_calculate_line(line) for line in normalized]
    totals = _totals(normalized, calculated)
    order.store, order.supplier = store, supplier
    for field, value in {**kwargs, "subtotal": totals["subtotal"], "igv_total": totals["igv_total"], "total_discount": totals["total_discount"], "total": totals["total"]}.items():
        setattr(order, field, value)
    order.full_clean(exclude=("created_by",))
    order.save()
    _replace_lines(order, normalized, calculated)
    _audit(order, "UPDATE", updated_by)
    return order


@transaction.atomic
def approve_purchase_order(order_id, *, company_id, approved_by=None):
    order = PurchaseOrder.objects.select_for_update().get(pk=order_id, company_id=company_id)
    if order.status != PurchaseOrderStatus.DRAFT:
        raise ValueError("Solo se pueden aprobar ordenes en borrador.")
    if not order.lines.exists():
        raise ValueError("La orden debe tener al menos una linea.")
    order.status = PurchaseOrderStatus.APPROVED
    order.save(update_fields=("status", "updated_at"))
    _audit(order, "APPROVE", approved_by)
    return order


@transaction.atomic
def cancel_purchase_order(order_id, *, company_id, cancelled_by=None):
    order = PurchaseOrder.objects.select_for_update().get(pk=order_id, company_id=company_id)
    if order.status == PurchaseOrderStatus.CLOSED:
        raise ValueError("Una orden cerrada no puede cancelarse.")
    order.status = PurchaseOrderStatus.CANCELLED
    order.save(update_fields=("status", "updated_at"))
    _audit(order, "CANCEL", cancelled_by)
    return order
