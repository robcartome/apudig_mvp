from decimal import Decimal
from django.test import TestCase

from apps.websites.catalog.quotation import confirm_cart_offer, recalculate_cart, validate_cart_items
from apps.websites.errors import WebsiteError
from .test_catalog import CommercialCatalogFixture


class CartQuotationTest(CommercialCatalogFixture, TestCase):
    def items(self, *, product=None, unit=None, quantity=1):
        return [{"productId": str((product or self.product).pk), "unitId": str((unit or self.pack).pk), "quantity": quantity}]

    def quote(self, items=None, host="a.catalog.test"):
        return recalculate_cart(host, self.items() if items is None else items)

    def test_authorized_price_unit_tax_and_zero_without_purchase_fallback(self):
        quote = self.quote()
        self.assertEqual(quote["items"][0]["unitPrice"], "70.80")
        self.assertEqual(quote["total"], "70.80")
        self.assertNotIn("priceListId", str(quote))
        self.assertNotIn("purchasePrice", str(quote))
        self.price.amount = Decimal("0")
        self.price.save()
        self.assertEqual(self.quote()["total"], "0.00")

    def test_live_price_changes_fingerprint_without_editorial_publication(self):
        initial = self.quote()
        self.price.amount = Decimal("12")
        self.price.save()
        updated = self.quote()
        self.assertEqual(updated["total"], "84.96")
        self.assertNotEqual(initial["offerFingerprint"], updated["offerFingerprint"])
        self.site.refresh_from_db()
        self.assertEqual(self.site.editorial_revision, 1)

    def test_confirmation_recalculates_and_rejects_an_old_offer(self):
        initial = self.quote()
        self.assertEqual(confirm_cart_offer("a.catalog.test", self.items(), initial["offerFingerprint"]), initial)
        with self.assertRaises(WebsiteError):
            confirm_cart_offer("a.catalog.test", self.items(), "ñ" * 64)
        self.price.amount = Decimal("12")
        self.price.save()
        with self.assertRaises(WebsiteError) as error:
            confirm_cart_offer("a.catalog.test", self.items(), initial["offerFingerprint"])
        self.assertEqual(error.exception.code, "OFFER_CHANGED")

    def test_joint_demand_of_base_and_pack_cannot_oversell_authorized_stock(self):
        combined = self.items() + self.items(unit=self.unit, quantity=3)
        with self.assertRaises(WebsiteError) as error:
            self.quote(combined)
        self.assertEqual(error.exception.code, "CART_UNAVAILABLE")
        self.assertEqual(len(error.exception.fields), 2)
        self.assertEqual(self.quote(self.items(unit=self.unit, quantity=8))["total"], "94.40")

    def test_missing_warehouse_configuration_is_unknown_not_fake_stock(self):
        self.configuration.warehouses.clear()
        self.assertEqual(self.quote(self.items(quantity=999))["items"][0]["availability"], "unknown")

    def test_removed_unpublished_foreign_or_unpriced_line_fails_whole_cart(self):
        for product in (self.foreign, self.unpublished):
            with self.subTest(product=product.pk), self.assertRaises(WebsiteError):
                self.quote(self.items(product=product))
        self.price.active = False
        self.price.save()
        with self.assertRaises(WebsiteError):
            self.quote()

    def test_unknown_domain_has_no_tenant_fallback(self):
        from apps.websites.models import Website
        with self.assertRaises(Website.DoesNotExist):
            self.quote(host="unknown.catalog.test")

    def test_unit_of_another_product_or_disabled_conversion_is_rejected(self):
        self.conversion.active = False
        self.conversion.save()
        with self.assertRaises(WebsiteError):
            self.quote()
        self.assertEqual(self.quote(self.items(unit=self.unit))["total"], "11.80")

    def test_strict_input_rejects_tampering_duplicates_and_invalid_quantities(self):
        line = self.items()[0]
        for items in ([], [line] * 201, [line, line], [{**line, "price": "0.01"}], [{**line, "company_id": str(self.b.pk)}], [{**line, "unitId": "bad"}]):
            with self.subTest(items=str(items)[:100]), self.assertRaises(WebsiteError):
                validate_cart_items(items)
        for quantity in (True, False, "1", 1.0, 0, -1, 1000, None):
            with self.subTest(quantity=quantity), self.assertRaises(WebsiteError):
                validate_cart_items([{**line, "quantity": quantity}])
