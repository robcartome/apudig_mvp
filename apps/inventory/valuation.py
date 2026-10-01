"""Canonical inventory valuation rules used by inventory reports."""
from decimal import Decimal


ZERO = Decimal("0")


def as_decimal(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))


def has_valid_inventory_cost(stock_quantity, inventory_unit_cost) -> bool:
    """A positive stock balance is valuated only when it has a positive cost."""
    return as_decimal(stock_quantity) <= ZERO or as_decimal(inventory_unit_cost) > ZERO


def inventory_valuation(stock_quantity, inventory_unit_cost):
    """Return stock value at average cost, or ``None`` when cost is missing."""
    stock = as_decimal(stock_quantity)
    cost = as_decimal(inventory_unit_cost)
    if not has_valid_inventory_cost(stock, cost):
        return None
    return stock * cost
