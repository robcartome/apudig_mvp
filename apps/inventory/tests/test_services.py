"""
inventory/tests/test_services.py — Tests de servicios de inventario.
"""
from decimal import Decimal

from django.test import TestCase

from apps.companies.models import Company, Store
from apps.inventory.models import (
    Category, Product, StockByWarehouse, Unit, Warehouse
)
from apps.inventory.services import register_entry, register_exit


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
