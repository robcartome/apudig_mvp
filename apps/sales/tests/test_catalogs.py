"""
sales/tests/test_catalogs.py — Tests de vistas de catálogos de ventas.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.companies.models import Company, Store
from apps.sales.models import BusinessDocumentType, DocumentSeries

User = get_user_model()


class CatalogViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="ventas@demo.com", password="test1234")
        self.company = Company.objects.create(name="Empresa Test", ruc="20000000099")
        self.store = Store.objects.create(company=self.company, name="Sucursal 1")

        self.client.login(username="ventas@demo.com", password="test1234")
        session = self.client.session
        session["active_company_id"] = str(self.company.id)
        session["active_store_id"] = str(self.store.id)
        session.save()

    # ── Series ────────────────────────────────────────────────────────────────

    def test_series_list_ok(self):
        resp = self.client.get(reverse("sales:series_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Series documentales")

    def test_series_create_get(self):
        resp = self.client.get(reverse("sales:series_create"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Nueva serie")

    def test_series_create_post_ok(self):
        resp = self.client.post(
            reverse("sales:series_create"),
            {
                "store": str(self.store.id),
                "voucher_type": "COT",
                "series": "C001",
                "active": "on",
            },
        )
        self.assertRedirects(resp, reverse("sales:series_list"))
        self.assertTrue(DocumentSeries.objects.filter(series="C001").exists())

    def test_series_create_duplicate_error(self):
        # Crear primero
        DocumentSeries.objects.create(
            company=self.company,
            store=self.store,
            voucher_type="COT",
            series="C001",
        )
        # Intentar duplicado
        resp = self.client.post(
            reverse("sales:series_create"),
            {
                "store": str(self.store.id),
                "voucher_type": "COT",
                "series": "C001",
                "active": "on",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(DocumentSeries.objects.filter(series="C001").count(), 1)

    def test_series_toggle(self):
        obj = DocumentSeries.objects.create(
            company=self.company,
            store=self.store,
            voucher_type="COT",
            series="T001",
            active=True,
        )
        resp = self.client.post(reverse("sales:series_toggle", args=[obj.pk]))
        self.assertRedirects(resp, reverse("sales:series_list"))
        obj.refresh_from_db()
        self.assertFalse(obj.active)

    # ── BusinessDocumentType ──────────────────────────────────────────────────

    def test_doctype_list_ok(self):
        resp = self.client.get(reverse("sales:doctype_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Tipos de documento")

    def test_doctype_create_ok(self):
        resp = self.client.post(
            reverse("sales:doctype_create"),
            {
                "code": "FAC",
                "name": "Factura Electrónica",
                "category": "SALES",
                "is_sunat": "on",
                "sunat_code": "01",
                "affects_stock": "on",
                "affects_accounting": "on",
                "active": "on",
            },
        )
        self.assertRedirects(resp, reverse("sales:doctype_list"))
        self.assertTrue(BusinessDocumentType.objects.filter(code="FAC").exists())

    def test_anonymous_redirect(self):
        self.client.logout()
        resp = self.client.get(reverse("sales:series_list"))
        self.assertEqual(resp.status_code, 302)

    def test_doctype_update_ok(self):
        obj = BusinessDocumentType.objects.create(
            code="BOL",
            name="Boleta de Venta",
            category="SALES",
        )
        resp = self.client.post(
            reverse("sales:doctype_update", args=[obj.pk]),
            {
                "code": "BOL",
                "name": "Boleta de Venta Actualizada",
                "category": "SALES",
                "is_sunat": "",
                "sunat_code": "",
                "affects_stock": "",
                "affects_accounting": "",
                "active": "on",
            },
        )
        self.assertRedirects(resp, reverse("sales:doctype_list"))
        obj.refresh_from_db()
        self.assertEqual(obj.name, "Boleta de Venta Actualizada")
