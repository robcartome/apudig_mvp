"""
sales/tests/test_quotations.py — Tests del módulo de cotizaciones.
"""
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.inventory.models import Category, Product, Unit
from apps.partners.models import CoreCustomer
from apps.sales.models import DocumentSeries, SalesQuotation
from apps.sales.services import (
    approve_quotation,
    cancel_quotation,
    create_quotation,
    reject_quotation,
    update_quotation,
)

from django.contrib.auth import get_user_model
User = get_user_model()


# ── Fixture helper ────────────────────────────────────────────────────────────

def _make_product(name="Producto Test", unit=None):
    if unit is None:
        unit, _ = Unit.objects.get_or_create(name="Unidad", defaults={"code": "UND"})
    cat, _ = Category.objects.get_or_create(name="General")
    sku = name.upper().replace(" ", "_")[:20]
    return Product.objects.create(
        name=name, sku=sku, category=cat, unit=unit,
        price_sale=Decimal("100.00"), active=True,
    )


def _make_line(product, qty="2", price="100.00"):
    return {
        "product": product,
        "description": "Desc",
        "quantity": Decimal(qty),
        "unit_price": Decimal(price),
        "discount_amount": Decimal("0"),
        "tax_type": "10",
        "igv_rate": Decimal("18"),
        "memo": "",
    }


class QuotationServiceTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Empresa Test", ruc="20000000099")
        self.store = Store.objects.create(company=self.company, name="Tienda 1")
        self.customer = CoreCustomer.objects.create(
            company=self.company,
            document_type="6",
            document_number="20999999999",
            legal_name="Cliente SAC",
        )
        self.series = DocumentSeries.objects.create(
            company=self.company, store=self.store, voucher_type="COT", series="C001",
        )
        self.product = _make_product()

    def _create(self, lines=None):
        if lines is None:
            lines = [_make_line(self.product)]
        return create_quotation(
            store_id=str(self.store.id),
            customer=self.customer,
            series=self.series,
            lines=lines,
            issue_date=timezone.now().date(),
        )

    def test_create_calculates_totals(self):
        q = self._create()
        # subtotal = 2 * 100 = 200, igv = 200 * 0.18 = 36, total = 236
        self.assertEqual(q.subtotal, Decimal("200.00"))
        self.assertEqual(q.igv_total, Decimal("36.00"))
        self.assertEqual(q.total, Decimal("236.00"))

    def test_create_assigns_series_number(self):
        q = self._create()
        self.assertEqual(q.series_code, "C001")
        self.assertEqual(q.number, 1)

    def test_series_number_increments(self):
        q1 = self._create()
        q2 = self._create()
        self.assertEqual(q2.number, q1.number + 1)

    def test_approve_transition(self):
        q = self._create()
        self.assertEqual(q.status, "DRAFT")
        approve_quotation(q.pk)
        q.refresh_from_db()
        self.assertEqual(q.status, "APPROVED")

    def test_approve_from_invalid_state_raises(self):
        q = self._create()
        approve_quotation(q.pk)
        with self.assertRaises(ValueError):
            approve_quotation(q.pk)  # APPROVED → APPROVED invalid

    def test_reject_transition(self):
        q = self._create()
        reject_quotation(q.pk)
        q.refresh_from_db()
        self.assertEqual(q.status, "REJECTED")

    def test_cancel_transition(self):
        q = self._create()
        cancel_quotation(q.pk)
        q.refresh_from_db()
        self.assertEqual(q.status, "CANCELLED")

    def test_update_quotation_only_if_draft(self):
        q = self._create()
        approve_quotation(q.pk)
        with self.assertRaises(ValueError):
            update_quotation(
                q.pk,
                lines=[_make_line(self.product)],
                issue_date=timezone.now().date(),
            )

    def test_update_quotation_recalculates_totals(self):
        q = self._create()
        update_quotation(
            q.pk,
            lines=[_make_line(self.product, qty="3", price="200.00")],
            issue_date=timezone.now().date(),
        )
        q.refresh_from_db()
        # subtotal = 3 * 200 = 600, igv = 108, total = 708
        self.assertEqual(q.subtotal, Decimal("600.00"))
        self.assertEqual(q.total, Decimal("708.00"))

    def test_exonerated_line_no_igv(self):
        line = _make_line(self.product)
        line["tax_type"] = "20"  # exonerado
        q = self._create(lines=[line])
        self.assertEqual(q.igv_total, Decimal("0.00"))
        self.assertEqual(q.total, q.subtotal)


class QuotationViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="test@demo.com", password="pass1234")
        self.company = Company.objects.create(name="Demo", ruc="20000000001")
        self.store = Store.objects.create(company=self.company, name="T1")
        self.customer = CoreCustomer.objects.create(
            company=self.company,
            document_type="6", document_number="20111111111", legal_name="Cliente Demo SAC"
        )
        self.series = DocumentSeries.objects.create(
            company=self.company, store=self.store, voucher_type="COT", series="C001",
        )
        self.product = _make_product("Prod A")
        self.client.login(username="test@demo.com", password="pass1234")
        s = self.client.session
        s["active_company_id"] = str(self.company.id)
        s["active_store_id"] = str(self.store.id)
        s.save()

    def test_list_ok(self):
        resp = self.client.get(reverse("sales:quotation_list"))
        self.assertEqual(resp.status_code, 200)

    def test_create_get(self):
        resp = self.client.get(reverse("sales:quotation_create"))
        self.assertEqual(resp.status_code, 200)

    def _post_create(self):
        today = timezone.now().date().isoformat()
        return self.client.post(reverse("sales:quotation_create"), {
            "store": str(self.store.id),
            "series": str(self.series.id),
            "customer": str(self.customer.id),
            "issue_date": today,
            "valid_until": "",
            "currency": "PEN",
            "notes": "",
            "internal_reference": "",
            # management form
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1",
            "lines-MAX_NUM_FORMS": "1000",
            # line 0
            "lines-0-product": str(self.product.id),
            "lines-0-description": "",
            "lines-0-quantity": "2",
            "lines-0-unit_price": "100",
            "lines-0-discount_amount": "0",
            "lines-0-tax_type": "10",
            "lines-0-igv_rate": "18",
            "lines-0-memo": "",
        })

    def test_create_post_ok(self):
        resp = self._post_create()
        self.assertEqual(SalesQuotation.objects.count(), 1)
        q = SalesQuotation.objects.first()
        self.assertRedirects(resp, reverse("sales:quotation_detail", args=[q.pk]))

    def test_detail_ok(self):
        self._post_create()
        q = SalesQuotation.objects.first()
        resp = self.client.get(reverse("sales:quotation_detail", args=[q.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "C001-00000001")

    def test_pdf_ok(self):
        self._post_create()
        q = SalesQuotation.objects.first()
        resp = self.client.get(reverse("sales:quotation_pdf", args=[q.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_approve_view(self):
        self._post_create()
        q = SalesQuotation.objects.first()
        resp = self.client.post(reverse("sales:quotation_approve", args=[q.pk]))
        self.assertRedirects(resp, reverse("sales:quotation_detail", args=[q.pk]))
        q.refresh_from_db()
        self.assertEqual(q.status, "APPROVED")

    def test_anonymous_redirect(self):
        self.client.logout()
        resp = self.client.get(reverse("sales:quotation_list"))
        self.assertEqual(resp.status_code, 302)
