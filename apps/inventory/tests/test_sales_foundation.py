from django.test import TestCase
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.inventory.models import (
    Movement,
    MovementOrigin,
    MovementType,
    Product,
    Unit,
    Warehouse,
)


class SalesInventoryFoundationTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Empresa", ruc="20987654321")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.warehouse = Warehouse.objects.create(store=self.store, name="General")
        self.unit = Unit.objects.create(code="NIU-T", name="Unidad")

    def test_products_track_inventory_by_default(self):
        product = Product.objects.create(
            company=self.company,
            name="Producto",
            sku="PROD-1",
            unit=self.unit,
        )
        self.assertTrue(product.tracks_inventory)

    def test_service_can_opt_out_of_inventory(self):
        service = Product.objects.create(
            company=self.company,
            name="Servicio",
            sku="SERV-1",
            unit=self.unit,
            tracks_inventory=False,
        )
        self.assertFalse(service.tracks_inventory)

    def test_warehouse_disallows_negative_stock_by_default(self):
        self.assertFalse(self.warehouse.allow_negative_stock)

    def test_sale_reversal_keeps_explicit_traceability(self):
        original = Movement.objects.create(
            type=MovementType.EXIT,
            origin=MovementOrigin.SALE,
            store=self.store,
            warehouse=self.warehouse,
            date=timezone.now(),
        )
        reversal = Movement.objects.create(
            type=MovementType.ENTRY,
            origin=MovementOrigin.SALE_REVERSAL,
            reversal_of=original,
            store=self.store,
            warehouse=self.warehouse,
            date=timezone.now(),
        )
        self.assertEqual(original.reversal, reversal)
        self.assertEqual(reversal.reversal_of, original)
