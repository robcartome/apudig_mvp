from decimal import Decimal, InvalidOperation
from django import template

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
