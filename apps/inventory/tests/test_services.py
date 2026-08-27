"""
inventory/tests/test_services.py — Tests de servicios de inventario.
"""
from decimal import Decimal

from django.test import TestCase

from apps.companies.models import Company, Store
from apps.inventory.models import (
    Category, MovementDetail, Product, ProductUnit, StockByWarehouse, Unit, Warehouse
)
from apps.inventory.services import register_entry, register_exit, register_transfer


class StockServiceTest(TestCase):
    def setUp(self):
        company = Company.objects.create(name="Demo", ruc="20999999001")
        store = Store.objects.create(company=company, name="Principal")
        unit = Unit.objects.create(code="NIU", name="Unidad")
        cat = Category.objects.create(code="GEN", name="General")
        self.warehouse = Warehouse.objects.create(store=store, name="Almacén 1")
        self.store_id = str(store.id)
        self.warehouse_id = str(self.warehouse.id)
        from django.utils import timezone
        self.product = Product.objects.create(
            name="Prod A", sku="SKU-A", unit=unit, category=cat,
            price_purchase=Decimal("10"), price_sale=Decimal("15"),
        )
        self.now = timezone.now()

    def _box_conversion(self, factor="20"):
        box = Unit.objects.create(code="BX", name="Caja")
        ProductUnit.objects.create(
            product=self.product, unit=self.product.unit, conversion_factor=1,
        )
        ProductUnit.objects.create(
            product=self.product, unit=box, conversion_factor=Decimal(factor),
        )
        return box

    def test_entry_increases_stock(self):
        register_entry(
            store_id=self.store_id,
            warehouse_id=self.warehouse_id,
            date=self.now,
            lines=[{"product_id": self.product.id, "quantity": Decimal("5"), "unit_price": Decimal("10")}],
        )
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal("5"))

    def test_exit_decreases_stock(self):
        register_entry(
            store_id=self.store_id, warehouse_id=self.warehouse_id, date=self.now,
            lines=[{"product_id": self.product.id, "quantity": Decimal("10"), "unit_price": Decimal("10")}],
        )
        register_exit(
            store_id=self.store_id, warehouse_id=self.warehouse_id, date=self.now,
            lines=[{"product_id": self.product.id, "quantity": Decimal("3"), "unit_price": Decimal("15")}],
        )
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal("7"))

    def test_alternate_unit_updates_stock_in_base_unit_and_keeps_snapshot(self):
        box = self._box_conversion()
        movement = register_entry(
            store_id=self.store_id, warehouse_id=self.warehouse_id, date=self.now,
            lines=[{"product_id": self.product.id, "unit_id": box.id,
                    "quantity": Decimal("2"), "unit_price": Decimal("180")}],
        )

        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        detail = MovementDetail.objects.get(movement=movement)
        self.assertEqual(stock.quantity, Decimal("40"))
        self.assertEqual(detail.quantity, Decimal("2"))
        self.assertEqual(detail.unit_code, "BX")
        self.assertEqual(detail.conversion_factor, Decimal("20"))
        self.assertEqual(detail.stock_quantity, Decimal("40"))

    def test_transfer_uses_converted_quantity_in_both_warehouses(self):
        box = self._box_conversion()
        destination = Warehouse.objects.create(store_id=self.store_id, name="Almacén 2")
        StockByWarehouse.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=Decimal("100")
        )

        register_transfer(
            store_id=self.store_id,
            warehouse_origin_id=self.warehouse_id,
            warehouse_dest_id=str(destination.id),
            date=self.now,
            lines=[{"product_id": self.product.id, "unit_id": box.id,
                    "quantity": Decimal("2"), "unit_price": Decimal("180")}],
        )

        origin_stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        destination_stock = StockByWarehouse.objects.get(product=self.product, warehouse=destination)
        self.assertEqual(origin_stock.quantity, Decimal("60"))
        self.assertEqual(destination_stock.quantity, Decimal("40"))
