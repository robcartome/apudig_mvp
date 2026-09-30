from decimal import Decimal, InvalidOperation
from django import template

from apps.core.currency import currency_symbol as get_currency_symbol

register = template.Library()

@register.filter
def smart_number(value):
    if value is None:
        return ""
    try:
        value = Decimal(value)
    except InvalidOperation:
        return value
    if value == value.to_integral_value():
        return f"{int(value)}"
    return f"{value.normalize()}"


@register.filter
def get_item(mapping, key):
    """Safe dictionary key access for templates."""
    if mapping is None:
        return None
    try:
        if key in mapping:
            return mapping.get(key)
        return mapping.get(str(key))
    except Exception:
        return None


@register.filter
def currency_symbol(value):
    """Render an ISO currency code as its human-facing symbol."""
    return get_currency_symbol(value)
