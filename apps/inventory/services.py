"""
inventory/services.py — Lógica transaccional de stock y movimientos.

CRÍTICO: Toda operación que modifique stock DEBE usar transaction.atomic()
para garantizar consistencia entre Movement, MovementDetail y StockByWarehouse.
"""
from decimal import Decimal

from django.db import transaction

from .models import Movement, MovementDetail, StockByWarehouse, Warehouse


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
        type="ENTRY",
        store_id=store_id,
        warehouse_id=warehouse_id,
        date=date,
        created_by=created_by,
        **kwargs,
    )
    _create_details_and_update_stock(movement, lines, delta=+1)
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
        type="EXIT",
        store_id=store_id,
        warehouse_id=warehouse_id,
        date=date,
        created_by=created_by,
        **kwargs,
    )
    _create_details_and_update_stock(movement, lines, delta=-1)
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
        type="TRANSFER",
        store_id=store_id,
        warehouse_origin_id=warehouse_origin_id,
        warehouse_dest_id=warehouse_dest_id,
        date=date,
        created_by=created_by,
        **kwargs,
    )
    _create_details_and_update_stock(movement, lines, delta=-1, warehouse_id=warehouse_origin_id)
    _update_stock_bulk(lines, warehouse_id=warehouse_dest_id, delta=+1)
    return movement


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
        )
    _update_stock_bulk(lines, warehouse_id=wh_id, delta=delta)


def _update_stock_bulk(lines: list[dict], warehouse_id: str, delta: int) -> None:
    for line in lines:
        stock, _ = StockByWarehouse.objects.select_for_update().get_or_create(
            product_id=line["product_id"],
            warehouse_id=warehouse_id,
            defaults={"quantity": Decimal("0")},
        )
        stock.quantity += Decimal(str(line["quantity"])) * delta
        stock.save(update_fields=["quantity"])
