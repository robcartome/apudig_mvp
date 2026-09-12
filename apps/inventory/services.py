"""
inventory/services.py — Lógica transaccional de stock y movimientos.

CRÍTICO: Toda operación que modifique stock DEBE usar transaction.atomic()
para garantizar consistencia entre Movement, MovementDetail y StockByWarehouse.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.companies.models import CompanyOperationalSettings, Store

from .models import (
    Movement,
    MovementAuditLog,
    MovementDetail,
    MovementStatus,
    MovementType,
    PriceList,
    Product,
    ProductUnit,
    ProductPrice,
    StockByWarehouse,
    Warehouse,
)


def _normalize_uom_lines(lines: list[dict]) -> list[dict]:
    normalized = []
    for raw in lines:
        line = dict(raw)
        product = Product.objects.select_related("unit").get(pk=line["product_id"])
        unit_id = line.get("unit_id") or product.unit_id
        conversion = ProductUnit.objects.select_related("unit").filter(
            product=product, unit_id=unit_id, active=True
        ).first()
        if conversion is None:
            if str(unit_id) != str(product.unit_id):
                raise ValueError(f"La unidad seleccionada no está habilitada para {product.name}.")
            conversion = ProductUnit.objects.create(
                product=product,
                unit=product.unit,
                conversion_factor=1,
                is_default_sale=True,
                is_default_purchase=True,
            )
        factor = Decimal(str(conversion.conversion_factor))
        line.update({
            "unit_id": conversion.unit_id,
            "unit_code": conversion.unit.code,
            "conversion_factor": factor,
            "stock_quantity": Decimal(str(line["quantity"])) * factor,
        })
        normalized.append(line)
    return normalized


@transaction.atomic
def register_entry(
    store_id: str,
    warehouse_id: str,
    date,
    lines: list[dict],
    created_by=None,
    **kwargs,
) -> Movement:
    """Guarda una entrada en borrador sin modificar existencias."""
    movement = Movement.objects.create(
        type=MovementType.ENTRY,
        status=MovementStatus.DRAFT,
        store_id=store_id,
        warehouse_id=warehouse_id,
        date=date,
        created_by=created_by,
        **kwargs,
    )
    _create_movement_details(movement, lines)
    _log_movement_audit(movement, MovementAuditLog.ActionType.CREATE, created_by, after_data=_movement_snapshot(movement))
    return movement


@transaction.atomic
def register_exit(
    store_id: str,
    warehouse_id: str,
    date,
    lines: list[dict],
    created_by=None,
    **kwargs,
) -> Movement:
    """Guarda una salida en borrador sin modificar existencias."""
    movement = Movement.objects.create(
        type=MovementType.EXIT,
        status=MovementStatus.DRAFT,
        store_id=store_id,
        warehouse_id=warehouse_id,
        date=date,
        created_by=created_by,
        **kwargs,
    )
    _create_movement_details(movement, lines)
    _log_movement_audit(movement, MovementAuditLog.ActionType.CREATE, created_by, after_data=_movement_snapshot(movement))
    return movement


@transaction.atomic
def register_transfer(
    store_id: str,
    warehouse_origin_id: str,
    warehouse_dest_id: str,
    date,
    lines: list[dict],
    created_by=None,
    **kwargs,
) -> Movement:
    """Guarda una transferencia en borrador sin modificar existencias."""
    movement = Movement.objects.create(
        type=MovementType.TRANSFER,
        status=MovementStatus.DRAFT,
        store_id=store_id,
        warehouse_origin_id=warehouse_origin_id,
        warehouse_dest_id=warehouse_dest_id,
        date=date,
        created_by=created_by,
        **kwargs,
    )
    _create_movement_details(movement, lines)
    _log_movement_audit(movement, MovementAuditLog.ActionType.CREATE, created_by, after_data=_movement_snapshot(movement))
    return movement


@transaction.atomic
def register_adjustment(
    store_id: str,
    warehouse_id: str,
    date,
    lines: list[dict],
    created_by=None,
    **kwargs,
) -> Movement:
    """Guarda un conteo físico en borrador sin modificar existencias."""
    movement = Movement.objects.create(
        type=MovementType.ADJUSTMENT,
        status=MovementStatus.DRAFT,
        store_id=store_id,
        warehouse_id=warehouse_id,
        date=date,
        created_by=created_by,
        **kwargs,
    )
    _create_adjustment_details(movement, lines)
    _log_movement_audit(movement, MovementAuditLog.ActionType.CREATE, created_by, after_data=_movement_snapshot(movement))
    return movement


@transaction.atomic
def confirm_movement(movement: Movement, confirmed_by=None) -> Movement:
    movement = Movement.objects.select_for_update().get(pk=movement.pk)

    if movement.status == MovementStatus.CONFIRMED:
        return movement
    if movement.status == MovementStatus.REVERSED:
        raise ValueError("El movimiento ya fue revertido.")
    if _lock_mode_enabled(movement) and _has_posterior_related_movements(movement):
        raise ValueError(
            "No se puede aplicar el movimiento con esta fecha porque existen operaciones "
            "aplicadas posteriores para el mismo producto y almacén."
        )

    before = _movement_snapshot(movement)

    _apply_existing_movement_stock(movement)

    movement.status = MovementStatus.CONFIRMED
    movement.confirmed_at = timezone.now()
    movement.confirmed_by = confirmed_by
    movement.save(update_fields=["status", "confirmed_at", "confirmed_by", "updated_at"])

    _log_movement_audit(
        movement,
        MovementAuditLog.ActionType.CONFIRM,
        confirmed_by,
        before_data=before,
        after_data=_movement_snapshot(movement),
        message="Movimiento aplicado al stock",
    )

    if movement.reversal_of_id:
        _mark_original_reversed(movement, changed_by=confirmed_by)
    return movement


@transaction.atomic
def update_movement(movement: Movement, *, lines: list[dict], updated_by=None, **kwargs) -> Movement:
    """Actualiza un borrador, que todavía no tiene impacto en stock."""
    movement = Movement.objects.select_for_update().get(pk=movement.pk)
    _ensure_movement_mutable(movement)
    before = _movement_snapshot(movement)

    movement.details.all().delete()

    for field, value in kwargs.items():
        setattr(movement, field, value)
    movement.save()

    if movement.type == MovementType.ADJUSTMENT:
        _create_adjustment_details(movement, lines)
    else:
        _create_movement_details(movement, lines)
    _log_movement_audit(
        movement,
        MovementAuditLog.ActionType.UPDATE,
        updated_by,
        before_data=before,
        after_data=_movement_snapshot(movement),
        message="Actualización en borrador",
    )
    return movement


@transaction.atomic
def delete_movement(movement: Movement, *, deleted_by=None) -> None:
    """Elimina un borrador; nunca revierte stock porque aún no fue aplicado."""
    movement = Movement.objects.select_for_update().get(pk=movement.pk)
    _ensure_movement_mutable(movement)
    before = _movement_snapshot(movement)
    _log_movement_audit(
        movement,
        MovementAuditLog.ActionType.DELETE,
        deleted_by,
        before_data=before,
        after_data=None,
        message="Eliminación de movimiento en borrador",
    )
    movement.delete()


# ── Helpers internos ───────────────────────────────────────────────────────────

def _create_movement_details(movement: Movement, lines: list[dict]) -> list[dict]:
    lines = _normalize_uom_lines(lines)
    for line in lines:
        MovementDetail.objects.create(
            movement=movement,
            product_id=line["product_id"],
            quantity=line["quantity"],
            unit_id=line["unit_id"], unit_code=line["unit_code"],
            conversion_factor=line["conversion_factor"], stock_quantity=line["stock_quantity"],
            unit_price=line.get("unit_price", Decimal("0")),
            location_id=line.get("location_id") or None,
        )
    return lines


def _create_adjustment_details(movement: Movement, lines: list[dict]) -> None:
    if not movement.warehouse_id:
        return

    lines = _normalize_uom_lines(lines)
    for line in lines:
        system_qty = (
            StockByWarehouse.objects
            .filter(product_id=line["product_id"], warehouse_id=movement.warehouse_id)
            .values_list("quantity", flat=True)
            .first()
            or Decimal("0")
        )
        physical_qty = line["stock_quantity"]
        difference = physical_qty - Decimal(str(system_qty))

        MovementDetail.objects.create(
            movement=movement,
            product_id=line["product_id"],
            quantity=difference,
            unit_id=line["unit_id"], unit_code=line["unit_code"],
            conversion_factor=line["conversion_factor"], stock_quantity=difference,
            unit_price=line.get("unit_price", Decimal("0")),
            physical_quantity=physical_qty,
            location_id=line.get("location_id") or None,
        )


def _movement_lines(movement: Movement) -> list[dict]:
    return [
        {
            "product_id": d.product_id,
            "quantity": d.quantity,
            "unit_id": d.unit_id,
            "stock_quantity": d.stock_quantity,
            "unit_price": d.unit_price,
            "product_name": d.product.name,
        }
        for d in movement.details.select_related("product")
    ]


def _apply_existing_movement_stock(movement: Movement) -> None:
    lines = _movement_lines(movement)
    if not lines:
        raise ValueError("El movimiento debe tener al menos un producto.")

    if movement.type == MovementType.ENTRY:
        if movement.warehouse_id:
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_id, delta=+1)
        return

    if movement.type == MovementType.EXIT:
        if movement.warehouse_id:
            _validate_available_stock(lines, movement.warehouse_id)
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_id, delta=-1)
        return

    if movement.type == MovementType.TRANSFER:
        if movement.warehouse_origin_id:
            _validate_available_stock(lines, movement.warehouse_origin_id)
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_origin_id, delta=-1)
        if movement.warehouse_dest_id:
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_dest_id, delta=+1)
        return

    if movement.type == MovementType.ADJUSTMENT:
        if not movement.warehouse_id:
            return
        for detail in movement.details.all():
            stock, _ = StockByWarehouse.objects.select_for_update().get_or_create(
                product_id=detail.product_id,
                warehouse_id=movement.warehouse_id,
                defaults={"quantity": Decimal("0")},
            )
            physical_qty = Decimal(str(detail.physical_quantity or 0))
            difference = physical_qty - Decimal(str(stock.quantity))
            detail.quantity = difference
            detail.stock_quantity = difference
            detail.save(update_fields=["quantity", "stock_quantity"])
            stock.quantity = physical_qty
            stock.save(update_fields=["quantity"])
        return


def _validate_available_stock(lines: list[dict], warehouse_id) -> None:
    warehouse = Warehouse.objects.select_related("store").get(pk=warehouse_id)
    if warehouse_allows_negative_stock(warehouse):
        return

    for line in lines:
        stock, _ = StockByWarehouse.objects.select_for_update().get_or_create(
            product_id=line["product_id"],
            warehouse_id=warehouse_id,
            defaults={"quantity": Decimal("0")},
        )
        required = Decimal(str(line["stock_quantity"]))
        if stock.quantity < required:
            raise ValueError(
                f"Stock insuficiente para {line['product_name']}. "
                f"Disponible: {_display_quantity(stock.quantity)}; "
                f"requerido: {_display_quantity(required)}."
            )


def warehouse_allows_negative_stock(warehouse: Warehouse) -> bool:
    """Resolve the warehouse override and the company-wide inventory policy."""
    if warehouse.allow_negative_stock:
        return True
    return CompanyOperationalSettings.objects.filter(
        company_id=warehouse.store.company_id,
        inventory_allow_negative_stock=True,
    ).exists()


def _display_quantity(value) -> str:
    """Show meaningful quantity precision without insignificant trailing zeroes."""
    return f"{Decimal(str(value)).normalize():f}"


def _ensure_movement_mutable(movement: Movement) -> None:
    """Only drafts are mutable; applied movements require a correction."""
    if movement.status != MovementStatus.DRAFT:
        raise ValueError(
            "El movimiento no está en borrador. Registre un nuevo movimiento correctivo para ajustar trazabilidad."
        )


def _mark_original_reversed(reversal: Movement, changed_by=None) -> None:
    original = Movement.objects.select_for_update().get(pk=reversal.reversal_of_id)
    if original.status == MovementStatus.REVERSED:
        return
    if original.status != MovementStatus.CONFIRMED:
        raise ValueError("Solo se puede revertir un movimiento aplicado.")

    before = _movement_snapshot(original)
    original.status = MovementStatus.REVERSED
    original.save(update_fields=["status", "updated_at"])
    _log_movement_audit(
        original,
        MovementAuditLog.ActionType.REVERSE,
        changed_by,
        before_data=before,
        after_data=_movement_snapshot(original),
        message=f"Revertido por {reversal.operation_code}",
    )


def _lock_mode_enabled(movement: Movement) -> bool:
    if not movement.store_id:
        return True
    if hasattr(movement, "store") and movement.store is not None:
        return bool(getattr(movement.store, "lock_movement_edits", True))
    lock_value = (
        Store.objects.filter(pk=movement.store_id)
        .values_list("lock_movement_edits", flat=True)
        .first()
    )
    return True if lock_value is None else bool(lock_value)


def _has_posterior_related_movements(movement: Movement) -> bool:
    product_ids = list(movement.details.values_list("product_id", flat=True))
    if not product_ids:
        return False

    warehouse_ids = {
        movement.warehouse_id,
        movement.warehouse_origin_id,
        movement.warehouse_dest_id,
    }
    warehouse_ids.discard(None)
    if not warehouse_ids:
        return False

    date_q = Q(date__gt=movement.date)
    if movement.created_at:
        date_q |= Q(date=movement.date, created_at__gt=movement.created_at)

    return (
        Movement.objects
        .exclude(pk=movement.pk)
        .filter(store_id=movement.store_id)
        .filter(status__in=(MovementStatus.CONFIRMED, MovementStatus.REVERSED))
        .filter(details__product_id__in=product_ids)
        .filter(date_q)
        .filter(
            Q(warehouse_id__in=warehouse_ids)
            | Q(warehouse_origin_id__in=warehouse_ids)
            | Q(warehouse_dest_id__in=warehouse_ids)
        )
        .distinct()
        .exists()
    )


def _movement_snapshot(movement: Movement) -> dict:
    return {
        "id": str(movement.id),
        "operation_code": movement.operation_code,
        "type": movement.type,
        "origin": movement.origin,
        "status": movement.status,
        "date": movement.date.isoformat() if movement.date else None,
        "store_id": str(movement.store_id) if movement.store_id else None,
        "warehouse_id": str(movement.warehouse_id) if movement.warehouse_id else None,
        "warehouse_origin_id": str(movement.warehouse_origin_id) if movement.warehouse_origin_id else None,
        "warehouse_dest_id": str(movement.warehouse_dest_id) if movement.warehouse_dest_id else None,
        "reason": movement.reason,
        "reference_doc": movement.reference_doc,
        "document_type_id": str(movement.document_type_id) if movement.document_type_id else None,
        "sales_document_id": str(movement.sales_document_id) if movement.sales_document_id else None,
        "purchase_document_id": str(movement.purchase_document_id) if movement.purchase_document_id else None,
        "series": movement.series,
        "number": movement.number,
        "details": [
            {
                "product_id": str(d.product_id),
                "quantity": str(d.quantity),
                "physical_quantity": str(d.physical_quantity) if d.physical_quantity is not None else None,
                "unit_price": str(d.unit_price),
                "location_id": str(d.location_id) if d.location_id else None,
            }
            for d in movement.details.all()
        ],
    }


def _log_movement_audit(movement, action, changed_by, before_data=None, after_data=None, message=""):
    MovementAuditLog.objects.create(
        movement=movement,
        action=action,
        changed_by=changed_by,
        before_data=before_data,
        after_data=after_data,
        message=message,
    )


def _update_stock_bulk(lines: list[dict], warehouse_id: str, delta: int) -> None:
    for line in lines:
        stock, _ = StockByWarehouse.objects.select_for_update().get_or_create(
            product_id=line["product_id"],
            warehouse_id=warehouse_id,
            defaults={"quantity": Decimal("0")},
        )
        stock.quantity += Decimal(str(line.get("stock_quantity", line["quantity"]))) * delta
        stock.save(update_fields=["quantity"])


# ── Listas de precio ──────────────────────────────────────────────────────────

def set_product_price(pricelist_id, product_id, amount, currency: str = "PEN") -> ProductPrice:
    """Crea o actualiza el precio de un producto en una lista de precios."""
    obj, _ = ProductPrice.objects.update_or_create(
        price_list_id=pricelist_id,
        product_id=product_id,
        defaults={"amount": amount, "currency": currency, "active": True},
    )
    return obj


def delete_product_price(pricelist_id, product_id) -> None:
    """Elimina el precio de un producto en una lista de precios (si existe)."""
    ProductPrice.objects.filter(
        price_list_id=pricelist_id, product_id=product_id
    ).delete()


@transaction.atomic
def create_price_list(name: str, description: str = "", active: bool = True, company_id=None) -> PriceList:
    return PriceList.objects.create(name=name, description=description, active=active, company_id=company_id)


def toggle_price_list(pricelist: PriceList) -> PriceList:
    pricelist.active = not pricelist.active
    pricelist.save(update_fields=["active"])
    return pricelist


def set_default_price_list(pricelist: PriceList) -> PriceList:
    """Marca esta lista como predeterminada y desmarca las demás de la misma empresa."""
    PriceList.objects.filter(company_id=pricelist.company_id, is_default=True).update(is_default=False)
    pricelist.is_default = True
    pricelist.save(update_fields=["is_default"])
    return pricelist
