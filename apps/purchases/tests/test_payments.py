from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.inventory.models import Product, Unit
from apps.partners.models import DocumentType, Supplier
from apps.purchases.models import PurchasePaymentStatus, SupplierPayment
from apps.purchases.payment_services import (
    cancel_supplier_payment, document_payment_summary, register_supplier_payment,
    replace_installment_schedule,
)
from apps.purchases.services import (
    cancel_purchase_document, create_purchase_document_draft, register_purchase_document,
)
from apps.sales.models import MeansOfPayment


class SupplierPaymentTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Empresa pagos compra", ruc="20911111111")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.supplier = Supplier.objects.create(company=self.company, name="Proveedor pago", document_number="20922222222")
        self.document_type = DocumentType.objects.create(code="FPG", name="Factura pago", category="BILLING")
        self.unit = Unit.objects.create(code="UPG", name="Unidad pago")
        self.product = Product.objects.create(company=self.company, name="Servicio pago", sku="PAG-1", unit=self.unit, tracks_inventory=False)
        self.means = MeansOfPayment.objects.create(company=self.company, name="Transferencia")
        self.document = create_purchase_document_draft(
            company_id=self.company.pk, store=self.store, supplier=self.supplier,
            document_type=self.document_type,
            lines=[{"product": self.product, "quantity": 1, "unit_price": 100, "tax_type": "10", "igv_rate": 18}],
            series="F001", number="900", issue_date=date(2026, 9, 1),
            due_date=date(2026, 9, 30), register_inventory_movement=False,
        )
        register_purchase_document(self.document.pk, company_id=self.company.pk)
        self.document.refresh_from_db()

    def pay(self, number, amount):
        return register_supplier_payment(
            company_id=self.company.pk, store=self.store, supplier=self.supplier,
            payment_number=number, payment_date=timezone.now(), currency="PEN", exchange_rate=1,
            means_of_payment=self.means,
            allocations=[{"installment": self.document.installments.get(), "amount": amount}],
        )

    def test_registering_document_creates_payable_installment(self):
        installment = self.document.installments.get()
        self.assertEqual(installment.amount, Decimal("118.00"))
        self.assertEqual(installment.due_date, date(2026, 9, 30))
        self.assertEqual(self.document.payment_status, PurchasePaymentStatus.UNPAID)

    def test_partial_and_full_payments_update_document_status(self):
        self.pay("PAG-001", Decimal("40"))
        self.document.refresh_from_db()
        self.assertEqual(self.document.payment_status, PurchasePaymentStatus.PARTIALLY_PAID)
        self.assertEqual(document_payment_summary(self.document)["balance"], Decimal("78.00"))
        self.pay("PAG-002", Decimal("78"))
        self.document.refresh_from_db()
        self.assertEqual(self.document.payment_status, PurchasePaymentStatus.PAID)
        self.assertEqual(document_payment_summary(self.document)["balance"], Decimal("0.00"))

    def test_payment_cannot_exceed_installment_balance(self):
        with self.assertRaisesRegex(ValueError, "supera el saldo"):
            self.pay("PAG-003", Decimal("119"))
        self.assertFalse(SupplierPayment.objects.exists())

    def test_cancelling_payment_restores_balance(self):
        payment = self.pay("PAG-004", Decimal("118"))
        cancel_supplier_payment(payment.pk, company_id=self.company.pk)
        self.document.refresh_from_db()
        self.assertEqual(self.document.payment_status, PurchasePaymentStatus.UNPAID)
        self.assertEqual(document_payment_summary(self.document)["balance"], Decimal("118.00"))

    def test_document_with_payment_cannot_be_cancelled(self):
        self.pay("PAG-005", Decimal("10"))
        with self.assertRaisesRegex(ValueError, "pagos registrados"):
            cancel_purchase_document(self.document.pk, company_id=self.company.pk)

    def test_document_can_be_split_into_multiple_installments_before_payment(self):
        replace_installment_schedule(self.document.pk, company_id=self.company.pk, schedule=[
            {"due_date": date(2026, 9, 15), "amount": Decimal("50")},
            {"due_date": date(2026, 9, 30), "amount": Decimal("68")},
        ])
        installments = list(self.document.installments.order_by("sequence"))
        self.assertEqual([item.amount for item in installments], [Decimal("50.00"), Decimal("68.00")])
        self.assertEqual([item.sequence for item in installments], [1, 2])

    def test_installment_schedule_must_equal_document_total(self):
        with self.assertRaisesRegex(ValueError, "suma de cuotas"):
            replace_installment_schedule(self.document.pk, company_id=self.company.pk, schedule=[
                {"due_date": date(2026, 9, 30), "amount": Decimal("100")},
            ])


class SupplierPaymentViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(name="Empresa vista pagos", ruc="20933333333")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.supplier = Supplier.objects.create(company=self.company, name="Proveedor vista pago", document_number="20944444444")
        self.document_type = DocumentType.objects.create(code="FPV", name="Factura vista pago", category="BILLING")
        unit = Unit.objects.create(code="UPV", name="Unidad vista pago")
        product = Product.objects.create(company=self.company, name="Servicio vista", sku="PV-1", unit=unit, tracks_inventory=False)
        self.means = MeansOfPayment.objects.create(company=self.company, name="Efectivo")
        self.document = create_purchase_document_draft(
            company_id=self.company.pk, store=self.store, supplier=self.supplier,
            document_type=self.document_type,
            lines=[{"product": product, "quantity": 1, "unit_price": 50, "tax_type": "20", "igv_rate": 0}],
            series="F001", number="901", issue_date=date(2026, 9, 1), register_inventory_movement=False,
        )
        register_purchase_document(self.document.pk, company_id=self.company.pk)
        self.user = get_user_model().objects.create_user(email="pagos@example.com", password="testpass")
        self.client.login(username="pagos@example.com", password="testpass")
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()

    def test_register_payment_from_document_and_show_accounts_payable(self):
        response = self.client.get(reverse("purchases:accounts_payable_list"))
        self.assertContains(response, "F001-901")
        response = self.client.post(reverse("purchases:payment_create", args=[self.document.pk]), {
            "payment_number": "PAG-WEB-1", "payment_date": "2026-09-02T10:00",
            "amount": "20", "means_of_payment": str(self.means.pk), "reference": "OP-123",
        })
        self.assertRedirects(response, reverse("purchases:document_detail", args=[self.document.pk]), fetch_redirect_response=False)
        self.document.refresh_from_db()
        self.assertEqual(self.document.payment_status, PurchasePaymentStatus.PARTIALLY_PAID)
        self.assertEqual(SupplierPayment.objects.get().amount, Decimal("20.00"))

    def test_list_exposes_quick_payment_modal_balance_and_last_payment_date(self):
        response = self.client.get(reverse("purchases:document_list"))
        self.assertContains(response, "Fecha de pago")
        self.assertContains(response, "Saldo por pagar")
        self.assertContains(response, 'id="quickPaymentModal"', html=False)
        self.assertContains(response, 'data-balance="50.00"', html=False)

        response = self.client.post(reverse("purchases:payment_create", args=[self.document.pk]), {
            "payment_number": "PAG-RAPIDO-1", "payment_date": "2026-09-03T11:00",
            "amount": "15", "means_of_payment": str(self.means.pk),
            "reference": "ADELANTO", "next": "list",
        })
        self.assertRedirects(response, reverse("purchases:document_list"), fetch_redirect_response=False)
        self.document.refresh_from_db()
        self.assertEqual(self.document.payment_status, PurchasePaymentStatus.PARTIALLY_PAID)

        response = self.client.get(reverse("purchases:document_list"))
        self.assertContains(response, "PEN 35.00")
        self.assertContains(response, "03/09/2026 11:00")
