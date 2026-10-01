"""Canonical commercial-price and tax calculations.

Catalog prices are final commercial prices. Document ``unit_price`` fields are
net unit values. This module is the only conversion boundary between them.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q


MONEY = Decimal("0.01")
UNIT_VALUE = Decimal("0.000001")
TAXED_AFFECTATIONS = frozenset({"10"})


def as_decimal(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))


def money(value) -> Decimal:
    return as_decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def unit_value(value) -> Decimal:
    return as_decimal(value).quantize(UNIT_VALUE, rounding=ROUND_HALF_UP)


def tax_rate_for_company(company_id, *, affectation_type="10", on_date=None) -> Decimal:
    if affectation_type not in TAXED_AFFECTATIONS:
        return Decimal("0.00")
    on_date = on_date or date.today()
    from apps.companies.models import CompanyOperationalSettings, TaxRate

    rule = (
        TaxRate.objects.filter(
            company_id=company_id,
            affectation_type=affectation_type,
            active=True,
            valid_from__lte=on_date,
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=on_date))
        .order_by("-is_default", "-valid_from")
        .first()
    )
    if rule:
        return rule.rate
    configured = CompanyOperationalSettings.objects.filter(company_id=company_id).values_list(
        "default_igv_rate", flat=True
    ).first()
    return as_decimal(configured if configured is not None else "18.00")


@dataclass(frozen=True)
class PriceBreakdown:
    final_price: Decimal
    unit_value: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    affectation_type: str


def split_final_price(final_price, *, affectation_type="10", tax_rate=0) -> PriceBreakdown:
    final = money(final_price)
    rate = as_decimal(tax_rate)
    if affectation_type not in TAXED_AFFECTATIONS or rate == 0:
        net = unit_value(final)
        tax = Decimal("0.00")
    else:
        net = unit_value(final / (Decimal("1") + rate / Decimal("100")))
        tax = money(final - net)
    return PriceBreakdown(final, net, rate, tax, affectation_type)


def gross_from_unit_value(value, *, affectation_type="10", tax_rate=0) -> Decimal:
    value = as_decimal(value)
    if affectation_type not in TAXED_AFFECTATIONS:
        return money(value)
    return money(value * (Decimal("1") + as_decimal(tax_rate) / Decimal("100")))


def resolve_commercial_price(product, *, price_list=None, unit_conversion=None, currency="PEN") -> Decimal | None:
    """Resolve a final catalog price without calculating document taxes."""
    amount = None
    if price_list is not None:
        row = product.prices.filter(price_list=price_list, currency=currency, active=True).first()
        amount = row.amount if row else None
    if amount is None and currency == "PEN":
        amount = product.price_sale
    if amount is None:
        return None
    if unit_conversion is not None:
        if currency == "PEN" and unit_conversion.sale_price is not None:
            return as_decimal(unit_conversion.sale_price)
        return as_decimal(amount) * as_decimal(unit_conversion.conversion_factor)
    return as_decimal(amount)
