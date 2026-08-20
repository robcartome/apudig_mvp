"""
sales/tests/test_quotations.py â€” Tests del mÃ³dulo de cotizaciones.
"""
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.inventory.models import Category, Product, Unit
from apps.partners.models import Customer, DocumentType
from apps.sales.models import DocumentSeries, SalesDocument, SalesQuotation
from apps.sales.services import (
    approve_quotation,
    cancel_quotation,
    create_quotation,
    create_document_from_quotation,
    reject_quotation,
    update_quotation,
)

from django.contrib.auth import get_user_model
User = get_user_model()


# â”€â”€ Fixture helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
        self.customer = Customer.objects.create(
            company=self.company,
            document_type="6",
            document_number="20999999999",
            legal_name="Cliente SAC",
        )
        self.series = DocumentSeries.objects.create(
            company=self.company, store=self.store, document_type=DocumentType.objects.get_or_create(code="COT", defaults={"name": "COT", "category": "INTERNAL"})[0], series="C001",
        )
        self.product = _make_product()
        self.sales_series = DocumentSeries.objects.create(
            company=self.company, store=self.store, document_type=DocumentType.objects.get_or_create(code="NV", defaults={"name": "NV", "category": "INTERNAL"})[0], series="NV01"
        )

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

    def test_create_accepts_manual_number_and_advances_series(self):
        quotation = create_quotation(
            store_id=str(self.store.id),
            customer=self.customer,
            series=self.series,
            lines=[_make_line(self.product)],
            issue_date=timezone.now().date(),
            number=25,
        )
        self.series.refresh_from_db()
        self.assertEqual(quotation.number, 25)
        self.assertEqual(self.series.current_number, 25)

    def test_duplicate_series_number_is_rejected(self):
        self._create()
        with self.assertRaisesRegex(ValueError, "Ya existe la cotización"):
            create_quotation(
                store_id=str(self.store.id),
                customer=self.customer,
                series=self.series,
                lines=[_make_line(self.product)],
                issue_date=timezone.now().date(),
                number=1,
            )

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
            approve_quotation(q.pk)  # APPROVED â†’ APPROVED invalid

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

    def test_approved_quotation_converts_once_and_copies_commercial_data(self):
        quotation = self._create()
        quotation.exchange_rate = Decimal("3.750000")
        quotation.notes = "Condiciones copiadas"
        quotation.internal_reference = "REF-COT"
        quotation.save(update_fields=["exchange_rate", "notes", "internal_reference"])
        approve_quotation(quotation.pk)

        document = create_document_from_quotation(
            quotation.pk,
            document_type=DocumentType.objects.get_or_create(code="NV", defaults={"name": "NV", "category": "INTERNAL"})[0],
            series=self.sales_series,
            register_inventory_movement=False,
        )
        self.assertEqual(document.source_quotation_id, quotation.pk)
        self.assertEqual(document.customer_id, quotation.customer_id)
        self.assertEqual(document.exchange_rate, Decimal("3.750000"))
        self.assertEqual(document.internal_reference, "REF-COT")
        self.assertEqual(document.lines.count(), quotation.lines.count())
        quotation.refresh_from_db()
        self.assertEqual(quotation.status, "APPROVED")

        with self.assertRaisesRegex(ValueError, "ya fue convertida"):
            create_document_from_quotation(
                quotation.pk,
                document_type=DocumentType.objects.get_or_create(code="NV", defaults={"name": "NV", "category": "INTERNAL"})[0],
                series=self.sales_series,
                register_inventory_movement=False,
            )


class QuotationViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="test@demo.com", password="pass1234")
        self.company = Company.objects.create(name="Demo", ruc="20000000001")
        self.store = Store.objects.create(company=self.company, name="T1")
        self.customer = Customer.objects.create(
            company=self.company,
            document_type="6", document_number="20111111111", legal_name="Cliente Demo SAC"
        )
        self.series = DocumentSeries.objects.create(
            company=self.company, store=self.store, document_type=DocumentType.objects.get_or_create(code="COT", defaults={"name": "COT", "category": "INTERNAL"})[0], series="C001",
        )
        self.product = _make_product("Prod A")
        self.sales_series = DocumentSeries.objects.create(
            company=self.company, store=self.store, document_type=DocumentType.objects.get_or_create(code="NV", defaults={"name": "NV", "category": "INTERNAL"})[0], series="NV01"
        )
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
        self.assertContains(resp, 'name="number"')
        self.assertContains(resp, 'id="edit-number-btn"')

    def _post_create(self, number=None):
        today = timezone.now().date().isoformat()
        data = {
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
        }
        if number is not None:
            data["number"] = str(number)
        return self.client.post(reverse("sales:quotation_create"), data)

    def test_create_post_ok(self):
        resp = self._post_create()
        self.assertEqual(SalesQuotation.objects.count(), 1)
        q = SalesQuotation.objects.first()
        self.assertRedirects(resp, reverse("sales:quotation_detail", args=[q.pk]))

    def test_duplicate_number_shows_form_error(self):
        self._post_create(number=7)
        response = self._post_create(number=7)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya existe la cotización C001-00000007")
        self.assertEqual(SalesQuotation.objects.count(), 1)

    def test_number_availability_api_reports_conflict(self):
        quotation = create_quotation(
            store_id=str(self.store.id), customer=self.customer, series=self.series,
            lines=[_make_line(self.product)], issue_date=timezone.now().date(), number=9,
        )
        response = self.client.get(
            reverse("sales:api_series_next_number", args=[self.series.pk]),
            {"number": "9"},
        )
        self.assertFalse(response.json()["available"])
        excluded = self.client.get(
            reverse("sales:api_series_next_number", args=[self.series.pk]),
            {"number": "9", "exclude": str(quotation.pk)},
        )
        self.assertTrue(excluded.json()["available"])

    def test_convert_approved_quotation_to_document(self):
        self._post_create()
        quotation = SalesQuotation.objects.get()
        approve_quotation(quotation.pk)
        response = self.client.post(
            reverse("sales:document_from_quotation", args=[quotation.pk]),
            {"series_id": str(self.sales_series.pk)},
        )
        document = SalesDocument.objects.get(source_quotation=quotation)
        self.assertRedirects(
            response,
            reverse("sales:document_detail", args=[document.pk]),
            fetch_redirect_response=False,
        )
        self.assertFalse(document.register_inventory_movement)

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

