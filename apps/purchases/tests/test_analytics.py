from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.inventory.models import Product, Unit, Warehouse
from apps.partners.models import DocumentType, Supplier
from apps.purchases.landed_cost_services import allocate_landed_cost
from apps.purchases.models import LandedCostAllocationMethod
from apps.purchases.order_services import approve_purchase_order, create_purchase_order
from apps.purchases.payment_services import register_supplier_payment
from apps.purchases.receipt_services import register_purchase_receipt
from apps.purchases.selectors import get_purchase_analytics
from apps.purchases.services import create_purchase_document_draft, register_purchase_document
from apps.sales.models import MeansOfPayment


class PurchaseAnalyticsTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Empresa analitica", ruc="20411111111")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.other_store = Store.objects.create(company=self.company, name="Secundaria")
        self.supplier = Supplier.objects.create(company=self.company, name="Proveedor analitico", document_number="20422222222")
        self.document_type = DocumentType.objects.create(code="FAN", name="Factura analitica", category="BILLING")
        self.unit = Unit.objects.create(code="UAN", name="Unidad analitica")
        self.product = Product.objects.create(company=self.company, name="Producto analitico", sku="AN-1", unit=self.unit)
        self.warehouse = Warehouse.objects.create(store=self.store, name="Almacen analitico")
        self.means = MeansOfPayment.objects.create(company=self.company, name="Transferencia analitica")
        self.document = self.make_document(self.store, "1", 100)
        allocate_landed_cost(
            document_id=self.document.pk, company_id=self.company.pk,
            description="Flete analitico", amount=10,
            allocation_method=LandedCostAllocationMethod.VALUE,
        )
        register_supplier_payment(
            company_id=self.company.pk, store=self.store, supplier=self.supplier,
            payment_number="PA-1", payment_date=timezone.now(), currency="PEN", exchange_rate=1,
            means_of_payment=self.means,
            allocations=[{"installment": self.document.installments.get(), "amount": 40}],
        )
        self.make_document(self.other_store, "2", 200)
        self.order = create_purchase_order(
            company_id=self.company.pk, store=self.store, supplier=self.supplier,
            order_number="OC-AN-1", order_date=date(2026, 9, 1),
            lines=[{"product": self.product, "quantity": 10, "unit_price": 10, "tax_type": "20", "igv_rate": 0}],
        )
        approve_purchase_order(self.order.pk, company_id=self.company.pk)
        register_purchase_receipt(
            order_id=self.order.pk, company_id=self.company.pk, warehouse=self.warehouse,
            receipt_number="REC-AN-1",
            receipt_date=timezone.make_aware(datetime(2026, 9, 2, 10, 0)),
            lines=[{"purchase_order_line": self.order.lines.get(), "quantity": 4}],
        )

    def make_document(self, store, number, price):
        document = create_purchase_document_draft(
            company_id=self.company.pk, store=store, supplier=self.supplier,
            document_type=self.document_type, series="F001", number=number,
            issue_date=date(2026, 9, 1), due_date=date(2026, 9, 30),
            register_inventory_movement=False,
            lines=[{"product": self.product, "quantity": 1, "unit_price": price, "tax_type": "20", "igv_rate": 0}],
        )
        register_purchase_document(document.pk, company_id=self.company.pk)
        document.refresh_from_db()
        return document

    def test_analytics_combines_commercial_financial_and_logistic_data(self):
        report = get_purchase_analytics(self.company.pk, self.store.pk)
        self.assertEqual(report["kpis"]["document_count"], 1)
        self.assertEqual(report["kpis"]["spend_pen"], Decimal("100.00"))
        self.assertEqual(report["kpis"]["paid_pen"], Decimal("40.00"))
        self.assertEqual(report["kpis"]["balance_pen"], Decimal("60.00"))
        self.assertEqual(report["kpis"]["landed_cost_pen"], Decimal("10.00"))
        self.assertEqual(report["kpis"]["ordered_qty"], Decimal("10.0000"))
        self.assertEqual(report["kpis"]["received_qty"], Decimal("4"))
        self.assertEqual(report["kpis"]["receipt_rate"], Decimal("40"))
        self.assertEqual(report["fulfillment_rows"][0]["pending"], Decimal("6.0000"))

    def test_analytics_http_and_csv_are_available(self):
        user = get_user_model().objects.create_user(email="analytics@example.com", password="testpass")
        client = Client()
        client.login(username="analytics@example.com", password="testpass")
        session = client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()
        response = client.get(reverse("purchases:analytics"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Analítica de compras")
        self.assertContains(response, "Proveedor analitico")
        response = client.get(reverse("purchases:analytics"), {"format": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("Proveedor analitico", response.content.decode("utf-8-sig"))
