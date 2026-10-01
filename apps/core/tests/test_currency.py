from django.template import Context, Template
from django.test import SimpleTestCase

from apps.core.currency import currency_label, currency_symbol


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
