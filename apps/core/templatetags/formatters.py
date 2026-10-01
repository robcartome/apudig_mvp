from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django import template
from django.utils.formats import number_format

from apps.core.currency import currency_symbol as get_currency_symbol

register = template.Library()

@register.filter
def smart_number(value):
    """Display quantities with the standard two decimal places for the UI.

    Storage precision is intentionally untouched. ``number_format`` keeps the
    configured locale's decimal separator while presenting a fixed precision.
    """
    if value is None:
        return ""
    try:
        value = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    if not value.is_finite():
        return ""
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return number_format(rounded, decimal_pos=2, use_l10n=True)


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
