"""
inventory/tests/test_services.py — Tests de servicios de inventario.
"""
from decimal import Decimal
from datetime import timedelta

from django.test import TestCase

from apps.companies.models import Company, Store
from apps.inventory.models import (
    Category, MovementDetail, MovementStatus, Product, ProductUnit,
    StockByWarehouse, Unit, Warehouse,
)
from apps.inventory.services import confirm_movement, register_entry, register_exit, register_transfer


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

    def test_entry_draft_does_not_change_stock_until_confirmation(self):
        movement = register_entry(
            store_id=self.store_id,
            warehouse_id=self.warehouse_id,
            date=self.now,
            lines=[{"product_id": self.product.id, "quantity": Decimal("5"), "unit_price": Decimal("10")}],
        )
        self.assertFalse(StockByWarehouse.objects.filter(product=self.product, warehouse=self.warehouse).exists())
        self.assertEqual(movement.status, MovementStatus.DRAFT)

        confirm_movement(movement)

        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal("5"))
        movement.refresh_from_db()
        self.assertEqual(movement.status, MovementStatus.CONFIRMED)

    def test_exit_decreases_stock(self):
        entry = register_entry(
            store_id=self.store_id, warehouse_id=self.warehouse_id, date=self.now,
            lines=[{"product_id": self.product.id, "quantity": Decimal("10"), "unit_price": Decimal("10")}],
        )
        confirm_movement(entry)
        exit_movement = register_exit(
            store_id=self.store_id, warehouse_id=self.warehouse_id, date=self.now,
            lines=[{"product_id": self.product.id, "quantity": Decimal("3"), "unit_price": Decimal("15")}],
        )
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal("10"))

        confirm_movement(exit_movement)
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, Decimal("7"))

    def test_alternate_unit_updates_stock_in_base_unit_and_keeps_snapshot(self):
        box = self._box_conversion()
        movement = register_entry(
            store_id=self.store_id, warehouse_id=self.warehouse_id, date=self.now,
            lines=[{"product_id": self.product.id, "unit_id": box.id,
                    "quantity": Decimal("2"), "unit_price": Decimal("180")}],
        )

        self.assertFalse(StockByWarehouse.objects.filter(product=self.product, warehouse=self.warehouse).exists())

        confirm_movement(movement)
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

        movement = register_transfer(
            store_id=self.store_id,
            warehouse_origin_id=self.warehouse_id,
            warehouse_dest_id=str(destination.id),
            date=self.now,
            lines=[{"product_id": self.product.id, "unit_id": box.id,
                    "quantity": Decimal("2"), "unit_price": Decimal("180")}],
        )

        origin_stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(origin_stock.quantity, Decimal("100"))
        self.assertFalse(StockByWarehouse.objects.filter(product=self.product, warehouse=destination).exists())

        confirm_movement(movement)
        origin_stock.refresh_from_db()
        destination_stock = StockByWarehouse.objects.get(product=self.product, warehouse=destination)
        self.assertEqual(origin_stock.quantity, Decimal("60"))
        self.assertEqual(destination_stock.quantity, Decimal("40"))

    def test_operation_codes_are_sequential_per_store_and_year(self):
        first = register_entry(
            store_id=self.store_id, warehouse_id=self.warehouse_id, date=self.now,
            lines=[{"product_id": self.product.id, "quantity": Decimal("1"), "unit_price": 0}],
        )
        second = register_entry(
            store_id=self.store_id, warehouse_id=self.warehouse_id, date=self.now,
            lines=[{"product_id": self.product.id, "quantity": Decimal("1"), "unit_price": 0}],
        )

        self.assertEqual(first.operation_code, f"MOV{self.now.year}00001")
        self.assertEqual(second.operation_code, f"MOV{self.now.year}00002")

        following_year_date = self.now + timedelta(days=366)
        following_year = register_entry(
            store_id=self.store_id, warehouse_id=self.warehouse_id,
            date=following_year_date,
            lines=[{"product_id": self.product.id, "quantity": Decimal("1"), "unit_price": 0}],
        )

        self.assertEqual(following_year.operation_code, f"MOV{following_year_date.year}00001")

    def test_later_movement_does_not_close_previous_applied_movement(self):
        first = register_entry(
            store_id=self.store_id, warehouse_id=self.warehouse_id, date=self.now,
            lines=[{"product_id": self.product.id, "quantity": Decimal("2"), "unit_price": 0}],
        )
        confirm_movement(first)
        second = register_entry(
            store_id=self.store_id, warehouse_id=self.warehouse_id,
            date=self.now + timedelta(minutes=1),
            lines=[{"product_id": self.product.id, "quantity": Decimal("1"), "unit_price": 0}],
        )
        confirm_movement(second)

        first.refresh_from_db()
        self.assertEqual(first.status, MovementStatus.CONFIRMED)

    def test_backdated_draft_remains_editable_but_cannot_be_applied(self):
        later = register_entry(
            store_id=self.store_id, warehouse_id=self.warehouse_id, date=self.now,
            lines=[{"product_id": self.product.id, "quantity": Decimal("2"), "unit_price": 0}],
        )
        confirm_movement(later)
        backdated = register_entry(
            store_id=self.store_id, warehouse_id=self.warehouse_id,
            date=self.now - timedelta(days=1),
            lines=[{"product_id": self.product.id, "quantity": Decimal("1"), "unit_price": 0}],
        )

        self.assertFalse(backdated.is_locked_for_changes)
        self.assertFalse(backdated.can_confirm)
        with self.assertRaisesMessage(ValueError, "operaciones aplicadas posteriores"):
            confirm_movement(backdated)

        backdated.refresh_from_db()
        self.assertEqual(backdated.status, MovementStatus.DRAFT)

    def test_confirmed_reversal_marks_original_reversed_and_nets_stock_to_zero(self):
        original = register_entry(
            store_id=self.store_id, warehouse_id=self.warehouse_id, date=self.now,
            lines=[{"product_id": self.product.id, "quantity": Decimal("2"), "unit_price": 0}],
        )
        confirm_movement(original)
        reversal = register_exit(
            store_id=self.store_id, warehouse_id=self.warehouse_id,
            date=self.now + timedelta(minutes=1), reversal_of=original,
            lines=[{"product_id": self.product.id, "quantity": Decimal("2"), "unit_price": 0}],
        )

        confirm_movement(reversal)

        original.refresh_from_db()
        reversal.refresh_from_db()
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(original.status, MovementStatus.REVERSED)
        self.assertEqual(reversal.status, MovementStatus.CONFIRMED)
        self.assertEqual(stock.quantity, Decimal("0"))
