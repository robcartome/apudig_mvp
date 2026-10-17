from decimal import Decimal

from django.test import SimpleTestCase

from apps.core.amount_words import amount_to_spanish_words, integer_to_spanish


class AmountWordsTest(SimpleTestCase):
    def test_example_amount_in_soles(self):
        self.assertEqual(
            amount_to_spanish_words(Decimal("3780.00"), "PEN"),
            "SON: TRES MIL SETECIENTOS OCHENTA CON 00/100 SOLES",
        )

    def test_rounds_cents_and_apocopates_before_currency(self):
        self.assertEqual(
            amount_to_spanish_words(Decimal("321.999"), "USD"),
            "SON: TRESCIENTOS VEINTIDÓS CON 00/100 DÓLARES AMERICANOS",
        )
        self.assertEqual(
            amount_to_spanish_words(Decimal("21.50"), "PEN"),
            "SON: VEINTIÚN CON 50/100 SOLES",
        )

    def test_supports_millions(self):
        self.assertEqual(
            integer_to_spanish(1_234_567),
            "UN MILLÓN DOSCIENTOS TREINTA Y CUATRO MIL QUINIENTOS SESENTA Y SIETE",
        )
