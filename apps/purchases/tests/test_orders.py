from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.inventory.models import Movement, Product, StockByWarehouse, Unit, Warehouse
from apps.partners.models import DocumentType, Supplier
from apps.purchases.models import (
    PurchaseDocument, PurchaseOrder, PurchaseOrderStatus,
)
from apps.purchases.order_services import approve_purchase_order, create_purchase_order
from apps.purchases.receipt_services import cancel_purchase_receipt, register_purchase_receipt
from apps.purchases.services import create_purchase_document_draft, register_purchase_document


class PurchaseOrderTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Empresa ordenes", ruc="20711111111")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.supplier = Supplier.objects.create(company=self.company, name="Proveedor orden", document_number="20722222222")
        self.unit = Unit.objects.create(code="UOC", name="Unidad orden")
        self.product = Product.objects.create(company=self.company, name="Producto orden", sku="OC-1", unit=self.unit)
        self.warehouse = Warehouse.objects.create(store=self.store, name="Almacen OC")

    def line(self):
        return {"product": self.product, "quantity": Decimal("2"), "unit_price": Decimal("10"), "tax_type": "10", "igv_rate": Decimal("18")}

    def receipt_datetime(self, day):
        return timezone.make_aware(datetime(2026, 9, day, 10, 0))

    def create_order(self):
        return create_purchase_order(
            company_id=self.company.pk, store=self.store, supplier=self.supplier,
            lines=[self.line()], order_number="OC-0001", order_date=date(2026, 9, 1),
        )

    def test_order_calculates_totals_without_inventory_effect(self):
        order = self.create_order()
        self.assertEqual(order.total, Decimal("23.60"))
        self.assertEqual(order.status, PurchaseOrderStatus.DRAFT)
        self.assertFalse(Movement.objects.exists())

    def test_approve_order_does_not_receive_or_invoice_goods(self):
        order = self.create_order()
        approve_purchase_order(order.pk, company_id=self.company.pk)
        order.refresh_from_db()
        self.assertEqual(order.status, PurchaseOrderStatus.APPROVED)
        self.assertFalse(Movement.objects.exists())
        self.assertFalse(PurchaseDocument.objects.exists())

    def test_multiple_partial_receipts_update_stock_and_close_order(self):
        order = self.create_order()
        approve_purchase_order(order.pk, company_id=self.company.pk)
        order_line = order.lines.get()
        first = register_purchase_receipt(
            order_id=order.pk, company_id=self.company.pk, warehouse=self.warehouse,
            receipt_number="REC-001", receipt_date=self.receipt_datetime(2),
            lines=[{"purchase_order_line": order_line, "quantity": Decimal("0.5")}],
        )
        order.refresh_from_db()
        self.assertEqual(order.status, PurchaseOrderStatus.APPROVED)
        self.assertEqual(first.inventory_movements.count(), 1)
        register_purchase_receipt(
            order_id=order.pk, company_id=self.company.pk, warehouse=self.warehouse,
            receipt_number="REC-002", receipt_date=self.receipt_datetime(3),
            lines=[{"purchase_order_line": order_line, "quantity": Decimal("1.5")}],
        )
        order.refresh_from_db()
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal("2"))
        self.assertEqual(order.status, PurchaseOrderStatus.CLOSED)

    def test_receipt_cannot_exceed_pending_quantity(self):
        order = self.create_order()
        approve_purchase_order(order.pk, company_id=self.company.pk)
        with self.assertRaisesRegex(ValueError, "supera el pendiente"):
            register_purchase_receipt(
                order_id=order.pk, company_id=self.company.pk, warehouse=self.warehouse,
                receipt_number="REC-003", receipt_date=self.receipt_datetime(2),
                lines=[{"purchase_order_line": order.lines.get(), "quantity": Decimal("3")}],
            )
        self.assertFalse(Movement.objects.exists())

    def test_cancel_receipt_reverses_stock_and_reopens_order(self):
        order = self.create_order()
        approve_purchase_order(order.pk, company_id=self.company.pk)
        receipt = register_purchase_receipt(
            order_id=order.pk, company_id=self.company.pk, warehouse=self.warehouse,
            receipt_number="REC-004", receipt_date=self.receipt_datetime(2),
            lines=[{"purchase_order_line": order.lines.get(), "quantity": Decimal("2")}],
        )
        cancel_purchase_receipt(receipt.pk, company_id=self.company.pk)
        order.refresh_from_db()
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal("0"))
        self.assertEqual(order.status, PurchaseOrderStatus.APPROVED)

    def test_invoice_line_is_matched_to_unique_order_line(self):
        order = self.create_order()
        document_type = DocumentType.objects.create(code="FOM", name="Factura matching", category="BILLING")
        document = create_purchase_document_draft(
            company_id=self.company.pk, store=self.store, supplier=self.supplier,
            purchase_order=order, document_type=document_type, lines=[self.line()],
            series="F001", number="503", issue_date=date(2026, 9, 1),
            register_inventory_movement=False,
        )
        self.assertEqual(document.lines.get().purchase_order_line_id, order.lines.get().pk)

    def test_linked_invoice_cannot_duplicate_order_receipt(self):
        order = self.create_order()
        document_type = DocumentType.objects.create(code="FOD", name="Factura no duplica", category="BILLING")
        document = create_purchase_document_draft(
            company_id=self.company.pk, store=self.store, supplier=self.supplier,
            purchase_order=order, document_type=document_type, lines=[self.line()],
            series="F001", number="504", issue_date=date(2026, 9, 1),
            register_inventory_movement=True, warehouse=self.warehouse,
        )
        with self.assertRaisesRegex(ValueError, "desde la orden"):
            register_purchase_document(document.pk, company_id=self.company.pk)
        self.assertFalse(Movement.objects.exists())

    def test_invoice_may_optionally_reference_order_from_same_supplier(self):
        order = self.create_order()
        document_type = DocumentType.objects.create(code="FOC", name="Factura OC", category="BILLING")
        document = PurchaseDocument(
            company=self.company, store=self.store, supplier=self.supplier,
            purchase_order=order, document_type=document_type,
            supplier_document_number=self.supplier.document_number,
            supplier_name=self.supplier.name, series="F001", number="500",
            issue_date=date(2026, 9, 1),
        )
        document.full_clean()

    def test_invoice_rejects_order_from_different_supplier(self):
        order = self.create_order()
        other = Supplier.objects.create(company=self.company, name="Otro proveedor", document_number="20733333333")
        document_type = DocumentType.objects.create(code="FO2", name="Factura OC 2", category="BILLING")
        document = PurchaseDocument(
            company=self.company, store=self.store, supplier=other,
            purchase_order=order, document_type=document_type,
            supplier_document_number=other.document_number, supplier_name=other.name,
            series="F001", number="501", issue_date=date(2026, 9, 1),
        )
        with self.assertRaises(ValidationError):
            document.full_clean()

        with self.assertRaisesRegex(ValueError, "mismo proveedor"):
            create_purchase_document_draft(
                company_id=self.company.pk, store=self.store, supplier=other,
                purchase_order=order, document_type=document_type, lines=[self.line()],
                series="F001", number="502", issue_date=date(2026, 9, 1),
            )


class PurchaseOrderViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(name="Empresa vista OC", ruc="20811111111")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.supplier = Supplier.objects.create(company=self.company, name="Proveedor vista OC", document_number="20822222222")
        self.unit = Unit.objects.create(code="UOV", name="Unidad orden vista")
        self.product = Product.objects.create(company=self.company, name="Producto vista OC", sku="OCV-1", unit=self.unit)
        self.warehouse = Warehouse.objects.create(store=self.store, name="Almacen vista OC")
        self.user = get_user_model().objects.create_user(email="ordenes@example.com", password="testpass")
        self.client.login(username="ordenes@example.com", password="testpass")
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()

    def payload(self):
        return {
            "supplier": str(self.supplier.pk), "order_number": "OC-100",
            "order_date": "2026-09-01", "currency": "PEN", "exchange_rate": "1",
            "lines-TOTAL_FORMS": "1", "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1", "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.pk), "lines-0-purchase_category": "",
            "lines-0-description": "Producto solicitado", "lines-0-unit": str(self.unit.pk),
            "lines-0-quantity": "2", "lines-0-unit_price": "10",
            "lines-0-discount_amount": "0", "lines-0-tax_type": "10", "lines-0-igv_rate": "18",
        }

    def test_create_and_view_purchase_order(self):
        response = self.client.post(reverse("purchases:order_create"), self.payload())
        if response.status_code == 200:
            self.fail((response.context["form"].errors, response.context["formset"].errors))
        order = PurchaseOrder.objects.get()
        self.assertRedirects(response, reverse("purchases:order_detail", args=[order.pk]), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("purchases:order_detail", args=[order.pk])).status_code, 200)

    def test_order_list_is_isolated_by_active_store(self):
        self.client.post(reverse("purchases:order_create"), self.payload())
        other_store = Store.objects.create(company=self.company, name="Secundaria")
        session = self.client.session
        session["active_store_id"] = str(other_store.pk)
        session.save()
        response = self.client.get(reverse("purchases:order_list"))
        self.assertNotContains(response, "OC-100")

    def test_receipt_form_registers_partial_inventory_entry(self):
        self.client.post(reverse("purchases:order_create"), self.payload())
        order = PurchaseOrder.objects.get()
        approve_purchase_order(order.pk, company_id=self.company.pk)
        line = order.lines.get()
        response = self.client.post(reverse("purchases:receipt_create", args=[order.pk]), {
            "warehouse": str(self.warehouse.pk), "receipt_number": "REC-WEB-1",
            "receipt_date": "2026-09-02T10:00", "notes": "Parcial",
            "lines-TOTAL_FORMS": "1", "lines-INITIAL_FORMS": "1",
            "lines-MIN_NUM_FORMS": "0", "lines-MAX_NUM_FORMS": "1000",
            "lines-0-purchase_order_line": str(line.pk), "lines-0-quantity": "1",
        })
        self.assertRedirects(response, reverse("purchases:order_detail", args=[order.pk]), fetch_redirect_response=False)
        self.assertEqual(StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse).quantity, Decimal("1"))
