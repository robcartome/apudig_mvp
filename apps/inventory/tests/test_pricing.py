from decimal import Decimal

from django.test import SimpleTestCase

from apps.inventory.pricing import gross_from_unit_value, split_final_price


class PricingContractTest(SimpleTestCase):
    def test_taxed_catalog_price_is_split_without_changing_final_price(self):
        result = split_final_price("118.00", affectation_type="10", tax_rate="18")

        self.assertEqual(result.final_price, Decimal("118.00"))
        self.assertEqual(result.unit_value, Decimal("100.000000"))
        self.assertEqual(result.tax_amount, Decimal("18.00"))

    def test_unaffected_price_is_already_the_unit_value(self):
        result = split_final_price("100.00", affectation_type="30", tax_rate="18")

        self.assertEqual(result.unit_value, Decimal("100.000000"))
        self.assertEqual(result.tax_amount, Decimal("0.00"))

    def test_unit_value_can_be_converted_back_to_commercial_price(self):
        self.assertEqual(
            gross_from_unit_value("100", affectation_type="10", tax_rate="18"),
            Decimal("118.00"),
        )
