"""
sales/tests/test_sales_documents.py — Tests del módulo de comprobantes.
"""
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.inventory.models import Category, Product, Unit
from apps.partners.models import Customer
from apps.sales.models import (
    DocumentSeries,
    SaleOrder,
    SalesDocument,
)
from apps.sales.services import (
    cancel_sales_document,
    confirm_order,
    create_credit_note,
    create_sale_order,
    create_sales_document_draft,
    issue_sales_document,
    void_sales_document,
)

from django.contrib.auth import get_user_model
User = get_user_model()


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _make_product(name="Producto Vch", unit=None):
    if unit is None:
        unit, _ = Unit.objects.get_or_create(name="Unidad Vch", defaults={"code": "UNV"})
    cat, _ = Category.objects.get_or_create(name="General")
    sku = ("VCH_" + name.upper().replace(" ", "_"))[:20]
    return Product.objects.create(
        name=name, sku=sku, category=cat, unit=unit,
        price_sale=Decimal("100.00"), active=True,
    )


def _make_line(product, qty="2", price="100.00"):
    return {
        "product": product,
        "description": "Línea test sales_document",
        "quantity": Decimal(qty),
        "unit_price": Decimal(price),
        "unit_code": "NIU",
        "discount_amount": Decimal("0"),
        "tax_type": "10",
        "igv_rate": Decimal("18"),
    }


class SalesDocumentServiceTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Empresa Vch", ruc="20333333333")
        self.store = Store.objects.create(company=self.company, name="Tienda Vch")
        self.customer = Customer.objects.create(
            company=self.company,
            document_type="6",
            document_number="20444444444",
            legal_name="Cliente Vch SAC",
        )
        self.fac_series = DocumentSeries.objects.create(
            company=self.company, store=self.store, document_type="01", series="F001",
        )
        self.cn_series = DocumentSeries.objects.create(
            company=self.company, store=self.store, document_type="07", series="FC01",
        )
        self.product = _make_product()

    def _create_draft(self, series=None, lines=None):
        return create_sales_document_draft(
            store_id=str(self.store.id),
            customer=self.customer,
            document_type="01",
            series=series or self.fac_series,
            lines=lines or [_make_line(self.product)],
            created_by=None,
            issue_date=timezone.now().date(),
            currency="PEN",
        )

    def test_create_draft_calculates_totals(self):
        v = self._create_draft()
        # qty=2 * price=100 = 200; igv=36; total=236
        self.assertEqual(v.subtotal, Decimal("200.00"))
        self.assertEqual(v.igv_total, Decimal("36.00"))
        self.assertEqual(v.total, Decimal("236.00"))
        self.assertEqual(v.status, "DRAFT")

    def test_draft_has_no_number(self):
        v = self._create_draft()
        self.assertEqual(v.number, "")

    def test_issue_assigns_number(self):
        v = self._create_draft()
        issued = issue_sales_document(v.pk)
        self.assertEqual(issued.status, "ISSUED")
        self.assertEqual(issued.number, "00000001")
        self.assertEqual(issued.series_code, "F001")

    def test_issue_increments_number(self):
        v1 = self._create_draft()
        v2 = self._create_draft()
        issue_sales_document(v1.pk)
        issue_sales_document(v2.pk)
        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual(v1.number, "00000001")
        self.assertEqual(v2.number, "00000002")

    def test_issue_requires_draft(self):
        v = self._create_draft()
        issue_sales_document(v.pk)
        with self.assertRaises(ValueError):
            issue_sales_document(v.pk)

    def test_issue_marks_order_invoiced(self):
        from apps.sales.models import BusinessDocumentType
        doc_type, _ = BusinessDocumentType.objects.get_or_create(
            code="OV_V", defaults={"name": "Orden Venta Vch", "category": "SALES"}
        )
        ov_series = DocumentSeries.objects.create(
            company=self.company, store=self.store, document_type="OV", series="OV0V",
        )
        order = create_sale_order(
            store_id=str(self.store.id),
            customer=self.customer,
            document_type=doc_type,
            series=ov_series,
            lines=[_make_line(self.product)],
            issue_date=timezone.now().date(),
        )
        confirm_order(order.pk)
        v = create_sales_document_draft(
            store_id=str(self.store.id),
            customer=self.customer,
            document_type="01",
            series=self.fac_series,
            lines=[_make_line(self.product)],
            sale_order=order,
            created_by=None,
            issue_date=timezone.now().date(),
            currency="PEN",
        )
        issue_sales_document(v.pk)
        order.refresh_from_db()
        self.assertEqual(order.status, "INVOICED")

    def test_void_issued(self):
        v = self._create_draft()
        issue_sales_document(v.pk)
        voided = void_sales_document(v.pk, reason="Error en datos")
        self.assertEqual(voided.status, "VOIDED")

    def test_void_requires_issued(self):
        v = self._create_draft()
        with self.assertRaises(ValueError):
            void_sales_document(v.pk)

    def test_cancel_draft(self):
        v = self._create_draft()
        cancelled = cancel_sales_document(v.pk)
        self.assertEqual(cancelled.status, "CANCELLED")

    def test_cancel_issued_raises(self):
        v = self._create_draft()
        issue_sales_document(v.pk)
        with self.assertRaises(ValueError):
            cancel_sales_document(v.pk)

    def test_credit_note_links_original(self):
        v = self._create_draft()
        issue_sales_document(v.pk)
        note = create_credit_note(
            sales_document_id=v.pk,
            reason_code="01",
            reason_description="Anulación",
            series=self.cn_series,
        )
        self.assertEqual(note.document_type, "07")
        self.assertEqual(note.reference_document_id, v.pk)
        self.assertEqual(note.note_reason_code, "01")
        self.assertEqual(note.lines.count(), v.lines.count())

    def test_credit_note_requires_issued(self):
        v = self._create_draft()  # still DRAFT
        with self.assertRaises(ValueError):
            create_credit_note(
                sales_document_id=v.pk,
                reason_code="01",
                reason_description="Test",
                series=self.cn_series,
            )


class SalesDocumentViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(name="Empresa Views Vch", ruc="20555555555")
        self.store = Store.objects.create(company=self.company, name="Tienda Views Vch")
        self.customer = Customer.objects.create(
            company=self.company,
            document_type="6",
            document_number="20666666666",
            legal_name="Cliente Views Vch SAC",
        )
        self.fac_series = DocumentSeries.objects.create(
            company=self.company, store=self.store, document_type="01", series="F002",
        )
        self.product = _make_product("Prod Views Vch")
        self.user = User.objects.create_user(email="vch@demo.com", password="pass1234")
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()

    def _login(self):
        self.client.login(username="vch@demo.com", password="pass1234")

    def _create_draft(self):
        return create_sales_document_draft(
            store_id=str(self.store.id),
            customer=self.customer,
            document_type="01",
            series=self.fac_series,
            lines=[_make_line(self.product)],
            created_by=self.user,
            issue_date=timezone.now().date(),
            currency="PEN",
        )

    def test_list_anonymous_redirect(self):
        resp = self.client.get(reverse("sales:document_list"))
        self.assertRedirects(resp, reverse("login"), fetch_redirect_response=False)

    def test_list_ok(self):
        self._login()
        resp = self.client.get(reverse("sales:document_list"))
        self.assertEqual(resp.status_code, 200)

    def test_create_get(self):
        self._login()
        resp = self.client.get(reverse("sales:document_create"))
        self.assertEqual(resp.status_code, 200)

    def test_create_post_ok(self):
        self._login()
        data = {
            "store": str(self.store.pk),
            "customer": str(self.customer.pk),
            "document_type": "01",
            "series": str(self.fac_series.pk),
            "issue_date": timezone.now().date().isoformat(),
            "currency": "PEN",
            "notes": "",
            # formset
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.pk),
            "lines-0-description": "desc",
            "lines-0-quantity": "2",
            "lines-0-unit_price": "100.00",
            "lines-0-discount_amount": "0",
            "lines-0-tax_type": "10",
            "lines-0-igv_rate": "18",
        }
        resp = self.client.post(reverse("sales:document_create"), data)
        self.assertEqual(SalesDocument.objects.filter(store=self.store).count(), 1)

    def test_detail_ok(self):
        self._login()
        v = self._create_draft()
        resp = self.client.get(reverse("sales:document_detail", kwargs={"pk": v.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_issue_view(self):
        self._login()
        v = self._create_draft()
        resp = self.client.post(reverse("sales:document_issue", kwargs={"pk": v.pk}))
        self.assertRedirects(
            resp,
            reverse("sales:document_detail", kwargs={"pk": v.pk}),
            fetch_redirect_response=False,
        )
        v.refresh_from_db()
        self.assertEqual(v.status, "ISSUED")

    def test_pdf_ok(self):
        self._login()
        v = self._create_draft()
        resp = self.client.get(reverse("sales:document_pdf", kwargs={"pk": v.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_cancel_view(self):
        self._login()
        v = self._create_draft()
        resp = self.client.post(reverse("sales:document_cancel", kwargs={"pk": v.pk}))
        self.assertRedirects(
            resp,
            reverse("sales:document_detail", kwargs={"pk": v.pk}),
            fetch_redirect_response=False,
        )
        v.refresh_from_db()
        self.assertEqual(v.status, "CANCELLED")
