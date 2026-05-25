"""
sales/tests/test_orders.py — Tests del módulo de órdenes de venta.
"""
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.inventory.models import Category, Product, Unit
from apps.partners.models import CoreCustomer
from apps.sales.models import (
    BusinessDocumentType,
    DocumentSeries,
    SaleOrder,
    SalesQuotation,
)
from apps.sales.services import (
    approve_quotation,
    cancel_order,
    confirm_order,
    create_order_from_quotation,
    create_quotation,
    create_sale_order,
    update_sale_order,
)

from django.contrib.auth import get_user_model
User = get_user_model()


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _make_product(name="Producto OV", unit=None):
    if unit is None:
        unit, _ = Unit.objects.get_or_create(name="Unidad", defaults={"code": "UND"})
    cat, _ = Category.objects.get_or_create(name="General")
    sku = ("OV_" + name.upper().replace(" ", "_"))[:20]
    return Product.objects.create(
        name=name, sku=sku, category=cat, unit=unit,
        price_sale=Decimal("50.00"), active=True,
    )


def _make_line(product, qty="3", price="50.00"):
    return {
        "product": product,
        "description": "Línea test",
        "quantity": Decimal(qty),
        "unit_price": Decimal(price),
        "discount_amount": Decimal("0"),
        "tax_type": "10",
        "igv_rate": Decimal("18"),
    }


class SaleOrderServiceTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Empresa OV", ruc="20000000001")
        self.store = Store.objects.create(company=self.company, name="Tienda OV")
        self.customer = CoreCustomer.objects.create(
            company=self.company,
            company=self.company,
            document_type="6",
            document_number="20111111111",
            legal_name="Cliente OV SAC",
        )
        self.doc_type = BusinessDocumentType.objects.create(
            code="OV01", name="Orden de Venta", category="SALES"
        )
        self.ov_series = DocumentSeries.objects.create(
            company=self.company, store=self.store, voucher_type="OV", series="OV01",
        )
        self.cot_series = DocumentSeries.objects.create(
            company=self.company, store=self.store, voucher_type="COT", series="C001",
        )
        self.product = _make_product()

    def _create_order(self, lines=None):
        if lines is None:
            lines = [_make_line(self.product)]
        return create_sale_order(
            store_id=str(self.store.id),
            customer=self.customer,
            document_type=self.doc_type,
            series=self.ov_series,
            lines=lines,
            issue_date=timezone.now().date(),
        )

    def test_create_calculates_totals(self):
        order = self._create_order()
        # subtotal = 3 * 50 = 150; igv = 150 * 0.18 = 27; total = 177
        self.assertEqual(order.subtotal, Decimal("150.00"))
        self.assertEqual(order.igv_total, Decimal("27.00"))
        self.assertEqual(order.total, Decimal("177.00"))

    def test_create_assigns_series_number(self):
        o1 = self._create_order()
        o2 = self._create_order()
        self.assertEqual(o1.series_code, "OV01")
        self.assertEqual(o1.number, "00000001")
        self.assertEqual(o2.number, "00000002")

    def test_confirm_order(self):
        order = self._create_order()
        self.assertEqual(order.status, "DRAFT")
        confirmed = confirm_order(order.pk)
        self.assertEqual(confirmed.status, "CONFIRMED")

    def test_confirm_requires_draft(self):
        order = self._create_order()
        confirm_order(order.pk)
        with self.assertRaises(ValueError):
            confirm_order(order.pk)

    def test_cancel_draft(self):
        order = self._create_order()
        cancelled = cancel_order(order.pk)
        self.assertEqual(cancelled.status, "CANCELLED")

    def test_cancel_confirmed(self):
        order = self._create_order()
        confirm_order(order.pk)
        cancelled = cancel_order(order.pk)
        self.assertEqual(cancelled.status, "CANCELLED")

    def test_cancel_cancelled_raises(self):
        order = self._create_order()
        cancel_order(order.pk)
        with self.assertRaises(ValueError):
            cancel_order(order.pk)

    def test_update_only_if_draft(self):
        order = self._create_order()
        confirm_order(order.pk)
        with self.assertRaises(ValueError):
            update_sale_order(order.pk, lines=[_make_line(self.product)])

    def test_update_recalculates(self):
        order = self._create_order()
        new_line = _make_line(self.product, qty="1", price="200.00")
        updated = update_sale_order(order.pk, lines=[new_line])
        # subtotal = 1 * 200 = 200; igv = 36; total = 236
        self.assertEqual(updated.subtotal, Decimal("200.00"))
        self.assertEqual(updated.total, Decimal("236.00"))

    def test_order_from_quotation(self):
        quot = create_quotation(
            store_id=str(self.store.id),
            customer=self.customer,
            series=self.cot_series,
            lines=[_make_line(self.product)],
            issue_date=timezone.now().date(),
        )
        approve_quotation(quot.pk)
        order = create_order_from_quotation(
            quotation_id=quot.pk,
            document_type=self.doc_type,
            series=self.ov_series,
        )
        self.assertEqual(order.status, "DRAFT")
        self.assertEqual(order.lines.count(), 1)
        # Quotation should be CANCELLED after conversion
        quot.refresh_from_db()
        self.assertEqual(quot.status, "CANCELLED")

    def test_order_from_quotation_requires_approved(self):
        quot = create_quotation(
            store_id=str(self.store.id),
            customer=self.customer,
            series=self.cot_series,
            lines=[_make_line(self.product)],
            issue_date=timezone.now().date(),
        )
        # Quotation still in DRAFT
        with self.assertRaises(ValueError):
            create_order_from_quotation(
                quotation_id=quot.pk,
                document_type=self.doc_type,
                series=self.ov_series,
            )


class SaleOrderViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(name="Empresa Views OV", ruc="20000000002")
        self.store = Store.objects.create(company=self.company, name="Tienda Views OV")
        self.customer = CoreCustomer.objects.create(
            document_type="6",
            document_number="20222222222",
            legal_name="Cliente Views OV SAC",
        )
        self.doc_type = BusinessDocumentType.objects.create(
            code="OV02", name="Orden de Venta B", category="SALES"
        )
        self.ov_series = DocumentSeries.objects.create(
            company=self.company, store=self.store, voucher_type="OV", series="OV02",
        )
        self.product = _make_product("Prod Views OV")
        self.user = User.objects.create_user(email="ov@demo.com", password="pass1234")
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()

    def _login(self):
        self.client.login(username="ov@demo.com", password="pass1234")

    def _create_order(self):
        return create_sale_order(
            store_id=str(self.store.id),
            customer=self.customer,
            document_type=self.doc_type,
            series=self.ov_series,
            lines=[_make_line(self.product)],
            issue_date=timezone.now().date(),
        )

    def test_list_anonymous_redirect(self):
        resp = self.client.get(reverse("sales:order_list"))
        self.assertRedirects(resp, reverse("login"), fetch_redirect_response=False)

    def test_list_ok(self):
        self._login()
        resp = self.client.get(reverse("sales:order_list"))
        self.assertEqual(resp.status_code, 200)

    def test_create_get(self):
        self._login()
        resp = self.client.get(reverse("sales:order_create"))
        self.assertEqual(resp.status_code, 200)

    def test_create_post_ok(self):
        self._login()
        data = {
            "store": str(self.store.pk),
            "customer": str(self.customer.pk),
            "document_type": str(self.doc_type.pk),
            "series": str(self.ov_series.pk),
            "issue_date": timezone.now().date().isoformat(),
            "due_date": "",
            "currency": "PEN",
            "payment_term_days": "0",
            "notes": "",
            "internal_reference": "",
            # formset
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.pk),
            "lines-0-description": "desc",
            "lines-0-quantity": "2",
            "lines-0-unit_price": "50.00",
            "lines-0-discount_amount": "0",
            "lines-0-tax_type": "10",
            "lines-0-igv_rate": "18",
        }
        resp = self.client.post(reverse("sales:order_create"), data)
        self.assertEqual(SaleOrder.objects.filter(store=self.store).count(), 1)

    def test_detail_ok(self):
        self._login()
        order = self._create_order()
        resp = self.client.get(reverse("sales:order_detail", kwargs={"pk": order.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_pdf_ok(self):
        self._login()
        order = self._create_order()
        resp = self.client.get(reverse("sales:order_pdf", kwargs={"pk": order.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_confirm_view(self):
        self._login()
        order = self._create_order()
        resp = self.client.post(reverse("sales:order_confirm", kwargs={"pk": order.pk}))
        self.assertRedirects(
            resp, reverse("sales:order_detail", kwargs={"pk": order.pk}),
            fetch_redirect_response=False,
        )
        order.refresh_from_db()
        self.assertEqual(order.status, "CONFIRMED")

    def test_cancel_view(self):
        self._login()
        order = self._create_order()
        resp = self.client.post(reverse("sales:order_cancel", kwargs={"pk": order.pk}))
        order.refresh_from_db()
        self.assertEqual(order.status, "CANCELLED")
