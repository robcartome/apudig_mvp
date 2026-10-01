from decimal import Decimal, ROUND_HALF_UP

from django.template import Context, Template
from django.test import SimpleTestCase
from django.utils.formats import number_format

from apps.core.currency import currency_label, currency_symbol
from apps.core.templatetags.formatters import smart_number


class CurrencyPresentationTest(SimpleTestCase):
    def test_known_currency_symbols(self):
        self.assertEqual(currency_symbol("PEN"), "S/.")
        self.assertEqual(currency_symbol("USD"), "$")
        self.assertEqual(currency_symbol("EUR"), "€")

    def test_unknown_currency_falls_back_to_iso_code(self):
        self.assertEqual(currency_symbol("xyz"), "XYZ")

    def test_currency_label_uses_symbol(self):
        self.assertEqual(currency_label("USD"), "Dólares estadounidenses ($)")

    def test_template_filter_is_available_globally(self):
        rendered = Template("{{ currency|currency_symbol }}").render(
            Context({"currency": "PEN"})
        )
        self.assertEqual(rendered, "S/.")

    def test_quantity_display_uses_two_localized_decimal_places(self):
        self.assertEqual(
            smart_number(Decimal("10.0000")),
            number_format(Decimal("10.0000"), decimal_pos=2, use_l10n=True),
        )
        self.assertEqual(
            smart_number(Decimal("2.5000")),
            number_format(Decimal("2.5000").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), decimal_pos=2, use_l10n=True),
        )
        self.assertEqual(
            smart_number(Decimal("2.555")),
            number_format(Decimal("2.56"), decimal_pos=2, use_l10n=True),
        )
