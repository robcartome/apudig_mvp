"""Currency presentation helpers.

ISO currency codes remain the canonical persisted and API values.  These
helpers are only for human-facing labels and amounts.
"""

CURRENCY_SYMBOLS = {
    "PEN": "S/.",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CNY": "¥",
    "CAD": "C$",
    "AUD": "A$",
    "CHF": "CHF",
    "BRL": "R$",
    "MXN": "MX$",
    "CLP": "CL$",
    "COP": "COL$",
    "ARS": "AR$",
    "BOB": "Bs.",
}

CURRENCY_NAMES = {
    "PEN": "Soles",
    "USD": "Dólares estadounidenses",
    "EUR": "Euros",
    "GBP": "Libras esterlinas",
    "JPY": "Yenes",
    "CNY": "Yuanes",
    "CAD": "Dólares canadienses",
    "AUD": "Dólares australianos",
    "CHF": "Francos suizos",
    "BRL": "Reales brasileños",
    "MXN": "Pesos mexicanos",
    "CLP": "Pesos chilenos",
    "COP": "Pesos colombianos",
    "ARS": "Pesos argentinos",
    "BOB": "Bolivianos",
}


def normalize_currency_code(code) -> str:
    return str(code or "").strip().upper()


def currency_symbol(code) -> str:
    """Return the display symbol, or the ISO code when no safe mapping exists."""
    normalized = normalize_currency_code(code)
    return CURRENCY_SYMBOLS.get(normalized, normalized)


def currency_label(code) -> str:
    normalized = normalize_currency_code(code)
    name = CURRENCY_NAMES.get(normalized, normalized)
    symbol = currency_symbol(normalized)
    return f"{name} ({symbol})" if name else ""


def currency_choices(codes=("PEN", "USD")):
    return tuple((code, currency_label(code)) for code in codes)
