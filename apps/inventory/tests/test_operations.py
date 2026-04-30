"""
inventory/tests/test_operations.py — Tests de movimientos y stock.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Store, UserCompanyAccess
from apps.inventory.models import Movement, Product, StockByWarehouse, Unit, Warehouse
from apps.users.models import User


class MovementViewsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="ops@demo.com", password="testpass")
        self.company = Company.objects.create(name="Demo Ops", ruc="20999999903")
        self.store = Store.objects.create(company=self.company, name="Principal")
        UserCompanyAccess.objects.create(
            user=self.user, company=self.company, store=self.store, is_default=True
        )
        self.unit = Unit.objects.create(code="UND", name="Unidad")
        self.warehouse = Warehouse.objects.create(store=self.store, name="Almacén A")
        self.product = Product.objects.create(
            name="Producto Test", sku="TEST-01", unit=self.unit,
            price_purchase=Decimal("10"), price_sale=Decimal("15"),
        )

        self.client.login(username="ops@demo.com", password="testpass")
        session = self.client.session
        session["active_company_id"] = str(self.company.id)
        session["active_store_id"] = str(self.store.id)
        session.save()

    def _post_movement(self, url, extra_data=None):
        now = timezone.now().strftime("%Y-%m-%dT%H:%M")
        data = {
            "date": now,
            "warehouse": str(self.warehouse.pk),
            "reason": "Test",
            "reference_doc": "",
            "supplier": "",
            "customer": "",
            "carrier": "",
            "document_type": "",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.pk),
            "lines-0-quantity": "5",
            "lines-0-unit_price": "10",
        }
        if extra_data:
            data.update(extra_data)
        return self.client.post(url, data)

    # ── Movement list ─────────────────────────────────────────────────────────

    def test_movement_list_ok(self):
        resp = self.client.get(reverse("inventory:movement_list"))
        self.assertEqual(resp.status_code, 200)

    # ── Entry ─────────────────────────────────────────────────────────────────

    def test_entry_create_get(self):
        resp = self.client.get(reverse("inventory:entry_create"))
        self.assertEqual(resp.status_code, 200)

    def test_entry_create_increases_stock(self):
        resp = self._post_movement(reverse("inventory:entry_create"))
        self.assertRedirects(resp, reverse("inventory:movement_list"))
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal("5"))
        self.assertEqual(Movement.objects.filter(type="ENTRY").count(), 1)

    def test_entry_creates_details(self):
        self._post_movement(reverse("inventory:entry_create"))
        mv = Movement.objects.get(type="ENTRY")
        self.assertEqual(mv.details.count(), 1)
        self.assertEqual(mv.details.first().quantity, Decimal("5"))

    # ── Exit ──────────────────────────────────────────────────────────────────

    def test_exit_create_decreases_stock(self):
        # First create stock
        self._post_movement(reverse("inventory:entry_create"))
        resp = self._post_movement(
            reverse("inventory:exit_create"),
            {"lines-0-quantity": "3"},
        )
        self.assertRedirects(resp, reverse("inventory:movement_list"))
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal("2"))  # 5 - 3

    # ── Transfer ──────────────────────────────────────────────────────────────

    def test_transfer_create(self):
        wh2 = Warehouse.objects.create(store=self.store, name="Almacén B")
        # Add stock to wh1 first
        self._post_movement(reverse("inventory:entry_create"))

        now = timezone.now().strftime("%Y-%m-%dT%H:%M")
        resp = self.client.post(reverse("inventory:transfer_create"), {
            "date": now,
            "warehouse_origin": str(self.warehouse.pk),
            "warehouse_dest": str(wh2.pk),
            "reason": "Traslado",
            "reference_doc": "",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.pk),
            "lines-0-quantity": "2",
            "lines-0-unit_price": "0",
        })
        self.assertRedirects(resp, reverse("inventory:movement_list"))
        stock_a = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        stock_b = StockByWarehouse.objects.get(product=self.product, warehouse=wh2)
        self.assertEqual(stock_a.quantity, Decimal("3"))  # 5 - 2
        self.assertEqual(stock_b.quantity, Decimal("2"))

    # ── Stock report ──────────────────────────────────────────────────────────

    def test_stock_report_ok(self):
        self._post_movement(reverse("inventory:entry_create"))
        resp = self.client.get(reverse("inventory:stock_report"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Producto Test")

    # ── Movement detail ───────────────────────────────────────────────────────

    def test_movement_detail_ok(self):
        self._post_movement(reverse("inventory:entry_create"))
        mv = Movement.objects.first()
        resp = self.client.get(reverse("inventory:movement_detail", args=[mv.pk]))
        self.assertEqual(resp.status_code, 200)
