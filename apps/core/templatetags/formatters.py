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
