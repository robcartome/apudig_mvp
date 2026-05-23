"""
inventory/services.py — Lógica transaccional de stock y movimientos.

CRÍTICO: Toda operación que modifique stock DEBE usar transaction.atomic()
para garantizar consistencia entre Movement, MovementDetail y StockByWarehouse.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.companies.models import Store

from .models import (
    Movement,
    MovementAuditLog,
    MovementDetail,
    MovementStatus,
    MovementType,
    PriceList,
    ProductPrice,
    StockByWarehouse,
    Warehouse,
)


@transaction.atomic
def register_entry(
    store_id: str,
    warehouse_id: str,
    date,
    lines: list[dict],
    created_by=None,
    **kwargs,
) -> Movement:
    """
    Registra una entrada de mercadería y actualiza el stock.

    lines: lista de dict con claves 'product_id', 'quantity', 'unit_price'.
    """
    movement = Movement.objects.create(
        type=MovementType.ENTRY,
        status=MovementStatus.DRAFT,
        store_id=store_id,
        warehouse_id=warehouse_id,
        date=date,
        created_by=created_by,
        **kwargs,
    )
    _create_details_and_update_stock(movement, lines, delta=+1)
    _log_movement_audit(movement, MovementAuditLog.ActionType.CREATE, created_by, after_data=_movement_snapshot(movement))
    _close_related_confirmed_movements(movement, changed_by=created_by)
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
    """Registra una salida de mercadería y descuenta stock."""
    movement = Movement.objects.create(
        type=MovementType.EXIT,
        status=MovementStatus.DRAFT,
        store_id=store_id,
        warehouse_id=warehouse_id,
        date=date,
        created_by=created_by,
        **kwargs,
    )
    _create_details_and_update_stock(movement, lines, delta=-1)
    _log_movement_audit(movement, MovementAuditLog.ActionType.CREATE, created_by, after_data=_movement_snapshot(movement))
    _close_related_confirmed_movements(movement, changed_by=created_by)
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
    """Transfiere mercadería entre almacenes dentro de la misma sucursal."""
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
    _create_details_and_update_stock(movement, lines, delta=-1, warehouse_id=warehouse_origin_id)
    _update_stock_bulk(lines, warehouse_id=warehouse_dest_id, delta=+1)
    _log_movement_audit(movement, MovementAuditLog.ActionType.CREATE, created_by, after_data=_movement_snapshot(movement))
    _close_related_confirmed_movements(movement, changed_by=created_by)
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
    """Registra un ajuste por conteo físico y sincroniza stock al valor contado."""
    movement = Movement.objects.create(
        type=MovementType.ADJUSTMENT,
        status=MovementStatus.DRAFT,
        store_id=store_id,
        warehouse_id=warehouse_id,
        date=date,
        created_by=created_by,
        **kwargs,
    )
    _create_adjustment_details_and_update_stock(movement, lines)
    _log_movement_audit(movement, MovementAuditLog.ActionType.CREATE, created_by, after_data=_movement_snapshot(movement))
    _close_related_confirmed_movements(movement, changed_by=created_by)
    return movement


@transaction.atomic
def confirm_movement(movement: Movement, confirmed_by=None) -> Movement:
    movement = Movement.objects.select_for_update().get(pk=movement.pk)

    if movement.status == MovementStatus.CLOSED:
        raise ValueError("El movimiento ya está cerrado.")

    if movement.status == MovementStatus.CONFIRMED:
        return movement

    before = _movement_snapshot(movement)

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
        message="Movimiento confirmado",
    )

    _close_if_posterior_exists(movement, changed_by=confirmed_by)
    return movement


@transaction.atomic
def update_movement(movement: Movement, *, lines: list[dict], updated_by=None, **kwargs) -> Movement:
    """
    Actualiza un movimiento existente recalculando su impacto en stock.

    El flujo es: revertir stock anterior -> actualizar cabecera y líneas -> aplicar stock nuevo.
    """
    movement = Movement.objects.select_for_update().get(pk=movement.pk)
    _ensure_movement_mutable(movement)
    before = _movement_snapshot(movement)

    _reverse_movement_stock(movement)
    movement.details.all().delete()

    for field, value in kwargs.items():
        setattr(movement, field, value)
    movement.save()

    _apply_movement_stock(movement, lines)
    _log_movement_audit(
        movement,
        MovementAuditLog.ActionType.UPDATE,
        updated_by,
        before_data=before,
        after_data=_movement_snapshot(movement),
        message="Actualización en borrador",
    )
    _close_if_posterior_exists(movement, changed_by=updated_by)
    _close_related_confirmed_movements(movement, changed_by=updated_by)
    return movement


@transaction.atomic
def delete_movement(movement: Movement, *, deleted_by=None) -> None:
    """Elimina un movimiento revirtiendo primero su impacto de stock."""
    movement = Movement.objects.select_for_update().get(pk=movement.pk)
    _ensure_movement_mutable(movement)
    before = _movement_snapshot(movement)
    _reverse_movement_stock(movement)
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

def _create_details_and_update_stock(
    movement: Movement, lines: list[dict], delta: int, warehouse_id: str | None = None
) -> None:
    wh_id = warehouse_id or movement.warehouse_id
    for line in lines:
        MovementDetail.objects.create(
            movement=movement,
            product_id=line["product_id"],
            quantity=line["quantity"],
            unit_price=line.get("unit_price", Decimal("0")),
            location_id=line.get("location_id") or None,
        )
    _update_stock_bulk(lines, warehouse_id=wh_id, delta=delta)


def _create_adjustment_details_and_update_stock(movement: Movement, lines: list[dict]) -> None:
    if not movement.warehouse_id:
        return

    for line in lines:
        stock, _ = StockByWarehouse.objects.select_for_update().get_or_create(
            product_id=line["product_id"],
            warehouse_id=movement.warehouse_id,
            defaults={"quantity": Decimal("0")},
        )

        physical_qty = Decimal(str(line.get("physical_quantity", line.get("quantity", 0))))
        difference = physical_qty - Decimal(str(stock.quantity))

        MovementDetail.objects.create(
            movement=movement,
            product_id=line["product_id"],
            quantity=difference,
            unit_price=line.get("unit_price", Decimal("0")),
            physical_quantity=physical_qty,
            location_id=line.get("location_id") or None,
        )

        stock.quantity = physical_qty
        stock.save(update_fields=["quantity"])


def _movement_lines(movement: Movement) -> list[dict]:
    return [
        {
            "product_id": d.product_id,
            "quantity": d.quantity,
            "unit_price": d.unit_price,
        }
        for d in movement.details.all()
    ]


def _reverse_movement_stock(movement: Movement) -> None:
    lines = _movement_lines(movement)
    if not lines:
        return

    if movement.type == MovementType.ENTRY:
        if movement.warehouse_id:
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_id, delta=-1)
        return

    if movement.type == MovementType.EXIT:
        if movement.warehouse_id:
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_id, delta=+1)
        return

    if movement.type == MovementType.TRANSFER:
        if movement.warehouse_origin_id:
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_origin_id, delta=+1)
        if movement.warehouse_dest_id:
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_dest_id, delta=-1)
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
            difference = Decimal(str(detail.quantity or 0))
            previous_system_qty = physical_qty - difference
            stock.quantity = previous_system_qty
            stock.save(update_fields=["quantity"])
        return


def _apply_movement_stock(movement: Movement, lines: list[dict]) -> None:
    if movement.type == MovementType.ADJUSTMENT:
        _create_adjustment_details_and_update_stock(movement, lines)
        return

    for line in lines:
        MovementDetail.objects.create(
            movement=movement,
            product_id=line["product_id"],
            quantity=line["quantity"],
            unit_price=line.get("unit_price", Decimal("0")),
            location_id=line.get("location_id") or None,
        )

    if movement.type == MovementType.ENTRY:
        if movement.warehouse_id:
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_id, delta=+1)
        return

    if movement.type == MovementType.EXIT:
        if movement.warehouse_id:
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_id, delta=-1)
        return

    if movement.type == MovementType.TRANSFER:
        if movement.warehouse_origin_id:
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_origin_id, delta=-1)
        if movement.warehouse_dest_id:
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_dest_id, delta=+1)
        return


def _ensure_movement_mutable(movement: Movement) -> None:
    """Regla ERP: solo se modifica en BORRADOR y sin bloqueo posterior activo."""
    if movement.status in (MovementStatus.CONFIRMED, MovementStatus.CLOSED):
        raise ValueError(
            "El movimiento no está en borrador. Registre un nuevo movimiento correctivo para ajustar trazabilidad."
        )

    if _lock_mode_enabled(movement) and _has_posterior_related_movements(movement):
        _close_if_posterior_exists(movement)
        raise ValueError(
            "El movimiento ya tiene operaciones posteriores relacionadas y quedó cerrado. "
            "Use un nuevo ajuste/movimiento correctivo en lugar de editar o eliminar."
        )


def _close_if_posterior_exists(movement: Movement, changed_by=None) -> None:
    if movement.status == MovementStatus.CLOSED:
        return
    if not _lock_mode_enabled(movement):
        return
    if not _has_posterior_related_movements(movement):
        return

    before = _movement_snapshot(movement)
    movement.status = MovementStatus.CLOSED
    movement.closed_at = timezone.now()
    movement.closed_by = changed_by
    movement.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])

    _log_movement_audit(
        movement,
        MovementAuditLog.ActionType.CLOSE,
        changed_by,
        before_data=before,
        after_data=_movement_snapshot(movement),
        message="Cierre automático por operaciones posteriores relacionadas",
    )


def _close_related_confirmed_movements(movement: Movement, changed_by=None) -> None:
    if not _lock_mode_enabled(movement):
        return

    product_ids = list(movement.details.values_list("product_id", flat=True))
    if not product_ids:
        return

    warehouse_ids = {
        movement.warehouse_id,
        movement.warehouse_origin_id,
        movement.warehouse_dest_id,
    }
    warehouse_ids.discard(None)
    if not warehouse_ids:
        return

    prev_date_q = Q(date__lt=movement.date)
    if movement.created_at:
        prev_date_q |= Q(date=movement.date, created_at__lt=movement.created_at)

    candidates = (
        Movement.objects
        .select_for_update()
        .filter(store_id=movement.store_id, status=MovementStatus.CONFIRMED)
        .exclude(pk=movement.pk)
        .filter(details__product_id__in=product_ids)
        .filter(prev_date_q)
        .filter(
            Q(warehouse_id__in=warehouse_ids)
            | Q(warehouse_origin_id__in=warehouse_ids)
            | Q(warehouse_dest_id__in=warehouse_ids)
        )
        .distinct()
    )

    for prev in candidates:
        before = _movement_snapshot(prev)
        prev.status = MovementStatus.CLOSED
        prev.closed_at = timezone.now()
        prev.closed_by = changed_by
        prev.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])
        _log_movement_audit(
            prev,
            MovementAuditLog.ActionType.CLOSE,
            changed_by,
            before_data=before,
            after_data=_movement_snapshot(prev),
            message=f"Cierre automático por movimiento posterior {movement.id}",
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
        "type": movement.type,
        "status": movement.status,
        "date": movement.date.isoformat() if movement.date else None,
        "store_id": str(movement.store_id) if movement.store_id else None,
        "warehouse_id": str(movement.warehouse_id) if movement.warehouse_id else None,
        "warehouse_origin_id": str(movement.warehouse_origin_id) if movement.warehouse_origin_id else None,
        "warehouse_dest_id": str(movement.warehouse_dest_id) if movement.warehouse_dest_id else None,
        "reason": movement.reason,
        "reference_doc": movement.reference_doc,
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
        stock.quantity += Decimal(str(line["quantity"])) * delta
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
def create_price_list(name: str, description: str = "", active: bool = True) -> PriceList:
    return PriceList.objects.create(name=name, description=description, active=active)


def toggle_price_list(pricelist: PriceList) -> PriceList:
    pricelist.active = not pricelist.active
    pricelist.save(update_fields=["active"])
    return pricelist
