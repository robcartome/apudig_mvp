from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase

from apps.companies.models import Company, Store
from apps.inventory.models import Brand, Category, MovementType, Product, StockByWarehouse, Unit, Warehouse
from apps.inventory.selectors import _kardex_delta, get_stock_comparative, get_stock_report_enhanced
from apps.inventory.valuation import inventory_valuation


class InventoryValuationRuleTest(TestCase):
    def test_positive_stock_without_average_cost_is_pending(self):
        self.assertIsNone(inventory_valuation(Decimal("5"), Decimal("0")))

    def test_zero_stock_without_cost_has_zero_value(self):
        self.assertEqual(inventory_valuation(Decimal("0"), Decimal("0")), Decimal("0"))


class InventoryValuationReportTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Valuation Co", ruc="20999999881")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.unit = Unit.objects.create(code="VAL", name="Unidad valoración")
        self.category = Category.objects.create(company=self.company, code="VAL", name="Valorizados")
        self.brand = Brand.objects.create(company=self.company, name="Marca V")
        self.warehouse_a = Warehouse.objects.create(store=self.store, name="A")
        self.warehouse_b = Warehouse.objects.create(store=self.store, name="B")

    def _product(self, sku, *, purchase, average, sale="20"):
        return Product.objects.create(
            company=self.company, name=sku, sku=sku, unit=self.unit,
            category=self.category, brand=self.brand,
            price_purchase=Decimal(purchase), inventory_unit_cost=Decimal(average),
            price_sale=Decimal(sale),
        )

    def test_reports_value_stock_at_average_cost_not_purchase_price(self):
        product = self._product("AVG-1", purchase="10", average="7")
        StockByWarehouse.objects.create(product=product, warehouse=self.warehouse_a, quantity=Decimal("5"))

        detail_rows = get_stock_report_enhanced(str(self.store.pk))
        _, comparative_rows, summary = get_stock_comparative(str(self.store.pk))

        self.assertEqual(detail_rows[0]["valuation"], Decimal("35"))
        self.assertEqual(comparative_rows[0]["total_valuation"], Decimal("35"))
        self.assertEqual(summary["grand_valuation"], Decimal("35"))

    def test_missing_cost_is_reported_and_excluded_from_partial_total(self):
        valued = self._product("VAL-1", purchase="10", average="8")
        pending = self._product("PEND-1", purchase="12", average="0")
        StockByWarehouse.objects.create(product=valued, warehouse=self.warehouse_a, quantity=Decimal("2"))
        StockByWarehouse.objects.create(product=pending, warehouse=self.warehouse_a, quantity=Decimal("3"))

        _, rows, summary = get_stock_comparative(str(self.store.pk))

        pending_row = next(row for row in rows if row["sku"] == "PEND-1")
        self.assertIsNone(pending_row["total_valuation"])
        self.assertEqual(summary["grand_valuation"], Decimal("16"))
        self.assertEqual(summary["products_pending_cost"], 1)
        self.assertTrue(summary["is_partial"])

    def test_warehouse_distribution_does_not_change_company_valuation(self):
        product = self._product("TRANSFER-1", purchase="30", average="25")
        StockByWarehouse.objects.create(product=product, warehouse=self.warehouse_a, quantity=Decimal("80"))
        StockByWarehouse.objects.create(product=product, warehouse=self.warehouse_b, quantity=Decimal("20"))

        _, _, summary = get_stock_comparative(str(self.store.pk))

        self.assertEqual(summary["grand_valuation"], Decimal("2500"))
        self.assertEqual(sum(item["valuation"] for item in summary["warehouse_rows"]), Decimal("2500"))

    def test_kardex_uses_base_stock_quantity_for_converted_units(self):
        detail = SimpleNamespace(quantity=Decimal("2"), stock_quantity=Decimal("40"))
        movement = SimpleNamespace(
            type=MovementType.ENTRY,
            warehouse_id=self.warehouse_a.pk,
            warehouse_origin_id=None,
            warehouse_dest_id=None,
        )

        self.assertEqual(_kardex_delta(movement, detail, str(self.warehouse_a.pk)), Decimal("40"))
