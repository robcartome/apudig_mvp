"""
inventory/services.py — Lógica transaccional de stock y movimientos.

CRÍTICO: Toda operación que modifique stock DEBE usar transaction.atomic()
para garantizar consistencia entre Movement, MovementDetail y StockByWarehouse.
"""
from decimal import Decimal

from django.db import transaction

from .models import Movement, MovementDetail, PriceList, ProductPrice, StockByWarehouse, Warehouse


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


@transaction.atomic
def update_movement(movement: Movement, *, lines: list[dict], **kwargs) -> Movement:
    """
    Actualiza un movimiento existente recalculando su impacto en stock.

    El flujo es: revertir stock anterior -> actualizar cabecera y líneas -> aplicar stock nuevo.
    """
    movement = Movement.objects.select_for_update().get(pk=movement.pk)
    _reverse_movement_stock(movement)
    movement.details.all().delete()

    for field, value in kwargs.items():
        setattr(movement, field, value)
    movement.save()

    _apply_movement_stock(movement, lines)
    return movement


@transaction.atomic
def delete_movement(movement: Movement) -> None:
    """Elimina un movimiento revirtiendo primero su impacto de stock."""
    movement = Movement.objects.select_for_update().get(pk=movement.pk)
    _reverse_movement_stock(movement)
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

    if movement.type == "ENTRY":
        if movement.warehouse_id:
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_id, delta=-1)
        return

    if movement.type == "EXIT":
        if movement.warehouse_id:
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_id, delta=+1)
        return

    if movement.type == "TRANSFER":
        if movement.warehouse_origin_id:
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_origin_id, delta=+1)
        if movement.warehouse_dest_id:
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_dest_id, delta=-1)


def _apply_movement_stock(movement: Movement, lines: list[dict]) -> None:
    for line in lines:
        MovementDetail.objects.create(
            movement=movement,
            product_id=line["product_id"],
            quantity=line["quantity"],
            unit_price=line.get("unit_price", Decimal("0")),
            location_id=line.get("location_id") or None,
        )

    if movement.type == "ENTRY":
        if movement.warehouse_id:
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_id, delta=+1)
        return

    if movement.type == "EXIT":
        if movement.warehouse_id:
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_id, delta=-1)
        return

    if movement.type == "TRANSFER":
        if movement.warehouse_origin_id:
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_origin_id, delta=-1)
        if movement.warehouse_dest_id:
            _update_stock_bulk(lines, warehouse_id=movement.warehouse_dest_id, delta=+1)


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
