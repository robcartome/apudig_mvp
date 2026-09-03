from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.companies.models import Company, Store
from apps.inventory.models import Product, Unit
from apps.partners.models import DocumentType, Supplier
from apps.purchases.landed_cost_services import (
    allocate_landed_cost, cancel_landed_cost, document_landed_cost_summary,
)
from apps.purchases.models import LandedCostAllocationMethod, PurchaseLandedCost
from apps.purchases.services import create_purchase_document_draft, register_purchase_document


class PurchaseLandedCostTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Empresa costos compra", ruc="20655555555")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.supplier = Supplier.objects.create(company=self.company, name="Proveedor costos", document_number="20666666666")
        self.document_type = DocumentType.objects.create(code="FLC", name="Factura landed", category="BILLING")
        self.unit = Unit.objects.create(code="ULC", name="Unidad landed")
        self.product_a = Product.objects.create(company=self.company, name="Producto A", sku="LC-A", unit=self.unit)
        self.product_b = Product.objects.create(company=self.company, name="Producto B", sku="LC-B", unit=self.unit)
        self.document = create_purchase_document_draft(
            company_id=self.company.pk, store=self.store, supplier=self.supplier,
            document_type=self.document_type, series="F001", number="LC-1",
            issue_date=date(2026, 9, 1), register_inventory_movement=False,
            lines=[
                {"product": self.product_a, "quantity": 1, "unit_price": 100, "tax_type": "20", "igv_rate": 0},
                {"product": self.product_b, "quantity": 3, "unit_price": 50, "tax_type": "20", "igv_rate": 0},
            ],
        )
        register_purchase_document(self.document.pk, company_id=self.company.pk)
        self.document.refresh_from_db()

    def test_allocate_by_value_preserves_invoiced_prices(self):
        original_prices = list(self.document.lines.values_list("unit_price", flat=True))
        cost = allocate_landed_cost(
            document_id=self.document.pk, company_id=self.company.pk,
            description="Flete", amount=30,
            allocation_method=LandedCostAllocationMethod.VALUE,
        )
        allocations = list(cost.allocations.order_by("purchase_document_line__position").values_list("amount", flat=True))
        self.assertEqual(allocations, [Decimal("12.00"), Decimal("18.00")])
        self.assertEqual(list(self.document.lines.values_list("unit_price", flat=True)), original_prices)
        self.assertEqual(document_landed_cost_summary(self.document)["total"], Decimal("30.00"))

    def test_allocate_by_quantity_uses_base_quantities(self):
        cost = allocate_landed_cost(
            document_id=self.document.pk, company_id=self.company.pk,
            description="Seguro", amount=30,
            allocation_method=LandedCostAllocationMethod.QUANTITY,
        )
        allocations = list(cost.allocations.order_by("purchase_document_line__position").values_list("amount", flat=True))
        self.assertEqual(allocations, [Decimal("7.50"), Decimal("22.50")])

    def test_manual_allocation_must_equal_charge(self):
        lines = list(self.document.lines.all())
        with self.assertRaisesRegex(ValueError, "suma de asignaciones"):
            allocate_landed_cost(
                document_id=self.document.pk, company_id=self.company.pk,
                description="Manual", amount=20,
                allocation_method=LandedCostAllocationMethod.MANUAL,
                manual_allocations=[{"line": lines[0], "amount": 5}, {"line": lines[1], "amount": 5}],
            )
        self.assertFalse(PurchaseLandedCost.objects.exists())

    def test_cancelled_charge_no_longer_affects_acquired_cost(self):
        cost = allocate_landed_cost(
            document_id=self.document.pk, company_id=self.company.pk,
            description="Transporte", amount=10,
            allocation_method=LandedCostAllocationMethod.VALUE,
        )
        cancel_landed_cost(cost.pk, company_id=self.company.pk)
        self.assertEqual(document_landed_cost_summary(self.document)["total"], Decimal("0.00"))


class PurchaseLandedCostViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(name="Empresa vista landed", ruc="20677777777")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.supplier = Supplier.objects.create(company=self.company, name="Proveedor vista landed", document_number="20688888888")
        document_type = DocumentType.objects.create(code="FLV", name="Factura vista landed", category="BILLING")
        unit = Unit.objects.create(code="ULV", name="Unidad vista landed")
        product = Product.objects.create(company=self.company, name="Producto vista landed", sku="LC-V", unit=unit)
        self.document = create_purchase_document_draft(
            company_id=self.company.pk, store=self.store, supplier=self.supplier,
            document_type=document_type, series="F001", number="LC-V1",
            issue_date=date(2026, 9, 1), register_inventory_movement=False,
            lines=[{"product": product, "quantity": 2, "unit_price": 40, "tax_type": "20", "igv_rate": 0}],
        )
        register_purchase_document(self.document.pk, company_id=self.company.pk)
        user = get_user_model().objects.create_user(email="landed@example.com", password="testpass")
        self.client.login(username="landed@example.com", password="testpass")
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()

    def test_create_landed_cost_from_document(self):
        line = self.document.lines.get()
        response = self.client.post(reverse("purchases:landed_cost_create", args=[self.document.pk]), {
            "description": "Flete local", "reference": "TR-1", "amount": "8",
            "allocation_method": "VALUE", "notes": "",
            "allocations-TOTAL_FORMS": "1", "allocations-INITIAL_FORMS": "1",
            "allocations-MIN_NUM_FORMS": "0", "allocations-MAX_NUM_FORMS": "1000",
            "allocations-0-line": str(line.pk), "allocations-0-amount": "0",
        })
        self.assertRedirects(response, reverse("purchases:document_detail", args=[self.document.pk]), fetch_redirect_response=False)
        self.assertEqual(PurchaseLandedCost.objects.get().amount, Decimal("8.00"))
