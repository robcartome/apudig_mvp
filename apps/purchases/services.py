from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.models import AuditLog
from apps.inventory.models import (
    Movement, MovementDetail, MovementOrigin, MovementStatus, MovementType,
    Product, ProductSupplier, ProductUnit,
)
from apps.inventory.services import confirm_movement, register_entry, register_exit

from .models import (
    PurchaseDocument,
    PurchaseDocumentLine,
    PurchaseDocumentReceiptMatch,
    PurchaseDocumentStatus,
)


MONEY = Decimal("0.01")


def _money(value):
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _normalize_line(line, company_id):
    product = line["product"]
    category = line.get("purchase_category")
    if bool(product) == bool(category):
        raise ValueError("La linea debe tener un producto o una categoria de compra.")
    if category:
        if str(category.company_id) != str(company_id):
            raise ValueError("La categoria de compra no pertenece a la empresa activa.")
        normalized = dict(line)
        normalized.update(
            product=None,
            unit=None,
            unit_code="ZZ",
            conversion_factor=Decimal("1"),
            stock_quantity=Decimal("0"),
        )
        return normalized
    if str(product.company_id) != str(company_id):
        raise ValueError("El producto no pertenece a la empresa activa.")

    requested_unit = line.get("unit")
    unit_id = getattr(requested_unit, "pk", requested_unit) or product.unit_id
    conversion = ProductUnit.objects.select_related("unit").filter(
        product=product, unit_id=unit_id, active=True
    ).first()
    if conversion:
        unit = conversion.unit
        factor = Decimal(str(conversion.conversion_factor))
    elif str(unit_id) == str(product.unit_id):
        unit = product.unit
        factor = Decimal("1")
    else:
        raise ValueError(f"La unidad seleccionada no esta habilitada para {product.name}.")

    normalized = dict(line)
    normalized.update(
        unit=unit,
        unit_code=unit.code,
        conversion_factor=factor,
        stock_quantity=Decimal(str(line["quantity"])) * factor,
    )
    return normalized


def _calculate_line(line):
    quantity = Decimal(str(line["quantity"]))
    unit_price = Decimal(str(line["unit_price"]))
    discount = Decimal(str(line.get("discount_amount") or 0))
    subtotal = quantity * unit_price - discount
    if subtotal < 0:
        raise ValueError("El descuento no puede superar el importe de la linea.")
    tax_type = line.get("tax_type", "10")
    igv_rate = Decimal(str(line.get("igv_rate") or 0))
    igv = subtotal * igv_rate / Decimal("100") if tax_type == "10" else Decimal("0")
    return {"subtotal": _money(subtotal), "igv_amount": _money(igv), "total": _money(subtotal + igv)}


def _totals(lines, calculated):
    totals = {
        "taxable_amount": Decimal("0"),
        "exempt_amount": Decimal("0"),
        "unaffected_amount": Decimal("0"),
        "igv_total": Decimal("0"),
        "total_discount": Decimal("0"),
    }
    buckets = {"10": "taxable_amount", "20": "exempt_amount", "30": "unaffected_amount", "40": "unaffected_amount"}
    for raw, calc in zip(lines, calculated):
        bucket = buckets.get(raw.get("tax_type", "10"))
        if bucket is None:
            raise ValueError("Tipo de impuesto no soportado.")
        totals[bucket] += calc["subtotal"]
        totals["igv_total"] += calc["igv_amount"]
        totals["total_discount"] += Decimal(str(raw.get("discount_amount") or 0))
    totals["subtotal"] = totals["taxable_amount"] + totals["exempt_amount"] + totals["unaffected_amount"]
    totals["total"] = totals["subtotal"] + totals["igv_total"]
    return {key: _money(value) for key, value in totals.items()}


def _validate_header(company_id, store, supplier, lines):
    if str(store.company_id) != str(company_id):
        raise ValueError("La sucursal no pertenece a la empresa activa.")
    if str(supplier.company_id) != str(company_id):
        raise ValueError("El proveedor no pertenece a la empresa activa.")
    if not lines:
        raise ValueError("El documento debe tener al menos una linea.")


def _validate_warehouse(store, warehouse):
    if warehouse and str(warehouse.store_id) != str(store.pk):
        raise ValueError("El almacen no pertenece a la sucursal del documento.")


def _validate_purchase_order(company_id, store, supplier, purchase_order):
    if not purchase_order:
        return
    if str(purchase_order.company_id) != str(company_id) or str(purchase_order.store_id) != str(store.pk):
        raise ValueError("La orden de compra no pertenece a la empresa y sucursal activas.")
    if str(purchase_order.supplier_id) != str(supplier.pk):
        raise ValueError("La orden de compra debe pertenecer al mismo proveedor.")


def _replace_lines(document, lines, calculated):
    document.lines.all().delete()
    order_line_map = {}
    if document.purchase_order_id:
        for order_line in document.purchase_order.lines.all():
            key = (order_line.product_id, order_line.purchase_category_id)
            order_line_map.setdefault(key, []).append(order_line)
    for position, (raw, calc) in enumerate(zip(lines, calculated), start=1):
        matching_order_lines = order_line_map.get((
            getattr(raw.get("product"), "pk", None),
            getattr(raw.get("purchase_category"), "pk", None),
        ), [])
        order_line = matching_order_lines.pop(0) if matching_order_lines else None
        PurchaseDocumentLine.objects.create(
            purchase_document=document,
            position=position,
            product=raw["product"],
            purchase_category=raw.get("purchase_category"),
            purchase_order_line=order_line,
            description=raw.get("description") or (raw["product"] or raw["purchase_category"]).name,
            product_code=raw.get("product_code") or (raw["product"].sku if raw["product"] else ""),
            quantity=raw["quantity"],
            unit=raw["unit"],
            unit_code=raw["unit_code"],
            conversion_factor=raw["conversion_factor"],
            stock_quantity=raw["stock_quantity"],
            unit_price=raw["unit_price"],
            discount_amount=raw.get("discount_amount") or 0,
            tax_type=raw.get("tax_type", "10"),
            igv_rate=raw.get("igv_rate") or 0,
            update_purchase_price=raw.get("update_purchase_price", True),
            memo=raw.get("memo", ""),
            **calc,
        )


def _replace_receipt_matches(document, receipt_movements):
    """Conciliar automáticamente ingresos confirmados contra líneas facturadas.

    La asignación usa cantidades base de stock. Un detalle de ingreso puede
    distribuirse entre varias facturas, pero nunca por encima de lo recibido.
    """
    movement_ids = {getattr(movement, "pk", movement) for movement in receipt_movements or []}
    if not movement_ids:
        return
    movements = list(
        # ``supplier`` es nullable y ``select_related`` genera un LEFT OUTER JOIN.
        # PostgreSQL solo debe bloquear la fila de Movement, no el lado opcional.
        Movement.objects.select_for_update(of=("self",)).filter(
            pk__in=movement_ids
        ).select_related("supplier")
    )
    if len(movements) != len(movement_ids):
        raise ValueError("Uno de los ingresos seleccionados no existe.")
    for movement in movements:
        if (
            movement.type != MovementType.ENTRY
            or movement.status != MovementStatus.CONFIRMED
            or movement.store_id != document.store_id
            or movement.supplier_id != document.supplier_id
        ):
            raise ValueError("Los ingresos relacionados deben estar confirmados y pertenecer al mismo proveedor y sucursal.")
        if movement.purchase_document_id and movement.purchase_document_id != document.pk:
            raise ValueError("Uno de los ingresos ya está vinculado a otra factura.")

    PurchaseDocumentReceiptMatch.objects.filter(
        purchase_document_line__purchase_document=document
    ).delete()
    lines = list(
        document.lines.select_related("product").filter(product__tracks_inventory=True)
    )
    details = list(
        MovementDetail.objects.select_for_update().filter(
            movement_id__in=movement_ids
        ).select_related("movement")
    )
    details_by_product = {}
    for detail in details:
        used = detail.purchase_receipt_matches.exclude(
            purchase_document_line__purchase_document=document
        ).aggregate(total=Sum("stock_quantity"))["total"] or Decimal("0")
        available = max(Decimal(str(detail.stock_quantity)) - used, Decimal("0"))
        if available:
            details_by_product.setdefault(detail.product_id, []).append([detail, available])

    matches_created = 0
    for line in lines:
        pending = Decimal(str(line.stock_quantity))
        for detail_data in details_by_product.get(line.product_id, []):
            detail, available = detail_data
            if pending <= 0:
                break
            allocated = min(pending, available)
            PurchaseDocumentReceiptMatch.objects.create(
                purchase_document_line=line,
                movement_detail=detail,
                stock_quantity=allocated,
            )
            matches_created += 1
            detail_data[1] -= allocated
            pending -= allocated
    if not matches_created:
        raise ValueError("Los ingresos seleccionados no contienen productos pendientes de esta factura.")


@transaction.atomic
def reconcile_purchase_document_receipts(document_id, *, company_id, receipt_movements):
    """Relaciona ingresos posteriores a una factura ya registrada."""
    document = PurchaseDocument.objects.select_for_update().get(
        pk=document_id, company_id=company_id
    )
    if document.document_status != PurchaseDocumentStatus.REGISTERED:
        raise ValueError("Solo se pueden conciliar recepciones de facturas registradas.")
    _replace_receipt_matches(document, receipt_movements)
    _audit(document, "RECONCILE_RECEIPT")
    return document



def _audit(document, action, user=None):
    AuditLog.objects.create(
        user=user,
        action=action,
        entity="PurchaseDocument",
        entity_id=str(document.pk),
        meta_data={
            "company_id": str(document.company_id),
            "store_id": str(document.store_id),
            "status": document.document_status,
            "series": document.series,
            "number": document.number,
        },
    )


def _update_current_purchase_prices(document):
    """Update current reference prices without changing historical purchase lines."""
    lines = list(
        document.lines.select_related("product").filter(
            update_purchase_price=True, product__isnull=False
        ).order_by("position")
    )
    if not lines:
        return
    product_ids = {line.product_id for line in lines}
    list(Product.objects.select_for_update().filter(pk__in=product_ids))
    relations = {
        relation.product_id: relation
        for relation in ProductSupplier.objects.select_for_update().filter(
            product_id__in=product_ids,
            supplier_id=document.supplier_id,
            active=True,
        )
    }
    currency_factor = document.exchange_rate if document.currency != "PEN" else Decimal("1")
    for line in lines:
        base_price = (
            Decimal(str(line.unit_price))
            * Decimal(str(currency_factor))
            / Decimal(str(line.conversion_factor))
        )
        Product.objects.filter(pk=line.product_id).update(
            price_purchase=base_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            updated_at=timezone.now(),
        )
        relation = relations.get(line.product_id)
        if relation:
            relation.purchase_price = base_price.quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )
            relation.save(update_fields=["purchase_price", "updated_at"])


@transaction.atomic
def create_purchase_document_draft(*, company_id, store, supplier, document_type, lines, created_by=None, **kwargs):
    receipt_movements = kwargs.pop("receipt_movements", None)
    _validate_header(company_id, store, supplier, lines)
    _validate_warehouse(store, kwargs.get("warehouse"))
    _validate_purchase_order(company_id, store, supplier, kwargs.get("purchase_order"))
    normalized = [_normalize_line(line, company_id) for line in lines]
    calculated = [_calculate_line(line) for line in normalized]
    totals = _totals(normalized, calculated)
    document = PurchaseDocument.objects.create(
        company_id=company_id,
        store=store,
        supplier=supplier,
        document_type=document_type,
        supplier_document_number=supplier.document_number,
        supplier_name=supplier.name,
        supplier_address=supplier.address,
        document_status=PurchaseDocumentStatus.DRAFT,
        created_by=created_by,
        **totals,
        **kwargs,
    )
    _replace_lines(document, normalized, calculated)
    _replace_receipt_matches(document, receipt_movements)
    _audit(document, "CREATE", created_by)
    return document


@transaction.atomic
def update_purchase_document_draft(document_id, *, company_id, store, supplier, document_type, lines, updated_by=None, **kwargs):
    receipt_movements = kwargs.pop("receipt_movements", None)
    document = PurchaseDocument.objects.select_for_update().get(pk=document_id, company_id=company_id)
    if document.document_status != PurchaseDocumentStatus.DRAFT:
        raise ValueError("Solo se pueden editar documentos en borrador.")
    _validate_header(company_id, store, supplier, lines)
    _validate_warehouse(store, kwargs.get("warehouse"))
    _validate_purchase_order(company_id, store, supplier, kwargs.get("purchase_order"))
    normalized = [_normalize_line(line, company_id) for line in lines]
    calculated = [_calculate_line(line) for line in normalized]
    totals = _totals(normalized, calculated)
    document.store = store
    document.supplier = supplier
    document.document_type = document_type
    document.supplier_document_number = supplier.document_number
    document.supplier_name = supplier.name
    document.supplier_address = supplier.address
    for field, value in {**kwargs, **totals}.items():
        setattr(document, field, value)
    document.full_clean(exclude=("created_by",))
    document.save()
    _replace_lines(document, normalized, calculated)
    _replace_receipt_matches(document, receipt_movements)
    _audit(document, "UPDATE", updated_by)
    return document


@transaction.atomic
def register_purchase_document(document_id, *, company_id, registered_by=None):
    document = (
        PurchaseDocument.objects
        .select_related("warehouse", "supplier", "document_type")
        # ``warehouse`` is optional, so select_related() produces a LEFT OUTER
        # JOIN. PostgreSQL cannot lock the nullable side of that join.  Only
        # the purchase document itself needs to be locked for this workflow.
        .select_for_update(of=("self",))
        .get(pk=document_id, company_id=company_id)
    )
    if document.document_status != PurchaseDocumentStatus.DRAFT:
        raise ValueError("Solo se pueden registrar documentos en borrador.")
    if not document.lines.exists():
        raise ValueError("El documento debe tener al menos una linea.")
    inventory_lines = list(
        document.lines.select_related("product", "unit").filter(product__tracks_inventory=True)
    )
    movement = None
    if document.purchase_order_id and document.register_inventory_movement and inventory_lines:
        raise ValueError(
            "La factura vinculada a una orden no debe recibir inventario. Registra la recepcion desde la orden de compra."
        )
    if document.register_inventory_movement and inventory_lines:
        if not document.warehouse_id:
            raise ValueError("Selecciona un almacen para registrar la recepcion.")
        if document.warehouse.store_id != document.store_id:
            raise ValueError("El almacen no pertenece a la sucursal del documento.")
        movement = register_entry(
            store_id=str(document.store_id),
            warehouse_id=str(document.warehouse_id),
            date=timezone.now(),
            lines=[
                {
                    "product_id": line.product_id,
                    "quantity": line.quantity,
                    "unit_id": line.unit_id,
                    "unit_price": line.unit_price,
                }
                for line in inventory_lines
            ],
            created_by=registered_by,
            origin=MovementOrigin.PURCHASE,
            purchase_document=document,
            supplier=document.supplier,
            document_type=document.document_type,
            series=document.series[:10],
            number=document.number[:20],
            reference_doc=str(document.pk),
            reason="Compra",
            description=f"Entrada por compra {document.series}-{document.number}",
        )
        confirm_movement(movement, confirmed_by=registered_by)
        _replace_receipt_matches(document, [movement])
    _update_current_purchase_prices(document)
    document.document_status = PurchaseDocumentStatus.REGISTERED
    document.save(update_fields=["document_status", "updated_at"])
    from .payment_services import ensure_document_installment
    ensure_document_installment(document)
    _audit(document, "REGISTER", registered_by)
    return document


@transaction.atomic
def cancel_purchase_document(document_id, *, company_id, cancelled_by=None):
    document = PurchaseDocument.objects.select_for_update().get(pk=document_id, company_id=company_id)
    if document.document_status == PurchaseDocumentStatus.CANCELLED:
        return document
    if document.installments.filter(
        payment_allocations__payment__status="REGISTERED"
    ).exists():
        raise ValueError("No se puede cancelar un documento con pagos registrados. Anula primero los pagos.")
    if document.landed_costs.filter(status="ALLOCATED").exists():
        raise ValueError("No se puede cancelar un documento con cargos adicionales activos. Anula primero los cargos.")
    originals = list(
        document.inventory_movements.select_for_update()
        .filter(origin=MovementOrigin.PURCHASE)
        .prefetch_related("details")
    )
    for original in originals:
        if hasattr(original, "reversal"):
            continue
        reversal = register_exit(
            store_id=str(document.store_id),
            warehouse_id=str(original.warehouse_id),
            date=timezone.now(),
            lines=[
                {
                    "product_id": detail.product_id,
                    "quantity": detail.quantity,
                    "unit_id": detail.unit_id,
                    "unit_price": detail.unit_price,
                }
                for detail in original.details.all()
            ],
            created_by=cancelled_by,
            origin=MovementOrigin.PURCHASE_REVERSAL,
            purchase_document=document,
            reversal_of=original,
            supplier=document.supplier,
            document_type=document.document_type,
            series=document.series[:10],
            number=document.number[:20],
            reference_doc=str(document.pk),
            reason="Cancelacion de compra",
            description=f"Reversion de compra {document.series}-{document.number}",
        )
        confirm_movement(reversal, confirmed_by=cancelled_by)
    document.document_status = PurchaseDocumentStatus.CANCELLED
    document.save(update_fields=["document_status", "updated_at"])
    _audit(document, "CANCEL", cancelled_by)
    return document


@transaction.atomic
def delete_purchase_document_draft(document_id, *, company_id, deleted_by=None):
    document = PurchaseDocument.objects.select_for_update().get(pk=document_id, company_id=company_id)
    if document.document_status != PurchaseDocumentStatus.DRAFT:
        raise ValueError("Solo se pueden eliminar documentos en borrador.")
    _audit(document, "DELETE", deleted_by)
    document.delete()
