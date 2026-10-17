"""Conversión de importes a letras para documentos comerciales en español."""

from decimal import Decimal, ROUND_HALF_UP


_SMALL = {
    0: "CERO", 1: "UNO", 2: "DOS", 3: "TRES", 4: "CUATRO", 5: "CINCO",
    6: "SEIS", 7: "SIETE", 8: "OCHO", 9: "NUEVE", 10: "DIEZ",
    11: "ONCE", 12: "DOCE", 13: "TRECE", 14: "CATORCE", 15: "QUINCE",
    16: "DIECISÉIS", 17: "DIECISIETE", 18: "DIECIOCHO", 19: "DIECINUEVE",
    20: "VEINTE", 21: "VEINTIUNO", 22: "VEINTIDÓS", 23: "VEINTITRÉS",
    24: "VEINTICUATRO", 25: "VEINTICINCO", 26: "VEINTISÉIS",
    27: "VEINTISIETE", 28: "VEINTIOCHO", 29: "VEINTINUEVE",
}
_TENS = {30: "TREINTA", 40: "CUARENTA", 50: "CINCUENTA", 60: "SESENTA", 70: "SETENTA", 80: "OCHENTA", 90: "NOVENTA"}
_HUNDREDS = {200: "DOSCIENTOS", 300: "TRESCIENTOS", 400: "CUATROCIENTOS", 500: "QUINIENTOS", 600: "SEISCIENTOS", 700: "SETECIENTOS", 800: "OCHOCIENTOS", 900: "NOVECIENTOS"}
_CURRENCIES = {
    "PEN": "SOLES",
    "USD": "DÓLARES AMERICANOS",
    "EUR": "EUROS",
}


def _under_thousand(number):
    if number < 30:
        return _SMALL[number]
    if number < 100:
        tens = number // 10 * 10
        unit = number % 10
        return _TENS[tens] if not unit else f"{_TENS[tens]} Y {_SMALL[unit]}"
    if number == 100:
        return "CIEN"
    hundreds = number // 100 * 100
    remainder = number % 100
    prefix = "CIENTO" if hundreds == 100 else _HUNDREDS[hundreds]
    return prefix if not remainder else f"{prefix} {_under_thousand(remainder)}"


def _apocopate(words):
    if words.endswith("VEINTIUNO"):
        return words[:-9] + "VEINTIÚN"
    if words.endswith(" Y UNO"):
        return words[:-6] + " Y UN"
    if words.endswith("UNO"):
        return words[:-3] + "UN"
    return words


def integer_to_spanish(number):
    number = int(number)
    if number < 0:
        return f"MENOS {integer_to_spanish(-number)}"
    if number < 1000:
        return _under_thousand(number)
    if number < 1_000_000:
        thousands, remainder = divmod(number, 1000)
        prefix = "MIL" if thousands == 1 else f"{_apocopate(integer_to_spanish(thousands))} MIL"
        return prefix if not remainder else f"{prefix} {integer_to_spanish(remainder)}"
    if number < 1_000_000_000_000:
        millions, remainder = divmod(number, 1_000_000)
        prefix = "UN MILLÓN" if millions == 1 else f"{_apocopate(integer_to_spanish(millions))} MILLONES"
        return prefix if not remainder else f"{prefix} {integer_to_spanish(remainder)}"
    if number < 1_000_000_000_000_000_000:
        billions, remainder = divmod(number, 1_000_000_000_000)
        prefix = "UN BILLÓN" if billions == 1 else f"{_apocopate(integer_to_spanish(billions))} BILLONES"
        return prefix if not remainder else f"{prefix} {integer_to_spanish(remainder)}"
    raise ValueError("El importe es demasiado grande para convertirlo a letras.")


def amount_to_spanish_words(value, currency="PEN"):
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    absolute = abs(amount)
    integer_part = int(absolute)
    cents = int((absolute - integer_part) * 100)
    words = _apocopate(integer_to_spanish(integer_part))
    if amount < 0:
        words = f"MENOS {words}"
    currency_name = _CURRENCIES.get((currency or "").upper(), (currency or "").upper())
    return f"SON: {words} CON {cents:02d}/100 {currency_name}".strip()
