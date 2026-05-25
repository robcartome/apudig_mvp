"""
partners/tests/test_views.py — Tests de vistas de socios.
"""
from django.test import TestCase
from django.urls import reverse

from apps.companies.models import Company, Store, UserCompanyAccess
from apps.partners.models import Carrier, CoreCustomer, Supplier
from apps.users.models import User


class PartnersViewsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="socios@demo.com", password="testpass")
        self.company = Company.objects.create(name="Demo SA", ruc="20999999902")
        self.store = Store.objects.create(company=self.company, name="Principal")
        UserCompanyAccess.objects.create(user=self.user, company=self.company, store=self.store, is_default=True)

        self.client.login(username="socios@demo.com", password="testpass")
        session = self.client.session
        session["active_company_id"] = str(self.company.id)
        session["active_store_id"] = str(self.store.id)
        session.save()

    # ── Customers ─────────────────────────────────────────────────────────────

    def test_customer_list_ok(self):
        CoreCustomer.objects.create(company=self.company, document_type="6", document_number="20123456789", legal_name="Empresa ABC")
        resp = self.client.get(reverse("partners:customer_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Empresa ABC")

    def test_customer_create_get(self):
        resp = self.client.get(reverse("partners:customer_create"))
        self.assertEqual(resp.status_code, 200)

    def test_customer_create_post(self):
        resp = self.client.post(reverse("partners:customer_create"), {
            "document_type": "6",
            "document_number": "20987654321",
            "legal_name": "Nuevo Cliente SA",
            "trade_name": "",
            "address": "",
            "phone": "",
            "email": "",
            "active": True,
            # profile_form fields
            "taxpayer_status": "",
            "taxpayer_condition": "",
            "is_retention_agent": False,
            "payment_term_days": 0,
            "notes": "",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(CoreCustomer.objects.filter(document_number="20987654321").exists())

    def test_customer_detail_ok(self):
        cust = CoreCustomer.objects.create(
            company=self.company, document_type="1", document_number="12345678", legal_name="Juan Pérez"
        )
        resp = self.client.get(reverse("partners:customer_detail", args=[cust.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Juan Pérez")

    def test_customer_search(self):
        CoreCustomer.objects.create(company=self.company, document_type="1", document_number="11111111", legal_name="Alpha Corp")
        CoreCustomer.objects.create(company=self.company, document_type="1", document_number="22222222", legal_name="Beta Corp")
        resp = self.client.get(reverse("partners:customer_list") + "?q=alpha")
        self.assertContains(resp, "Alpha Corp")
        self.assertNotContains(resp, "Beta Corp")

    def test_customer_delete(self):
        cust = CoreCustomer.objects.create(company=self.company, document_type="1", document_number="99999999", legal_name="Borrar")
        resp = self.client.post(reverse("partners:customer_delete", args=[cust.pk]))
        self.assertRedirects(resp, reverse("partners:customer_list"))
        self.assertFalse(CoreCustomer.objects.filter(pk=cust.pk).exists())

    # ── Suppliers ─────────────────────────────────────────────────────────────

    def test_supplier_list_ok(self):
        Supplier.objects.create(company=self.company, name="Dist. Sur", document_number="20111111111")
        resp = self.client.get(reverse("partners:supplier_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Dist. Sur")

    def test_supplier_create_post(self):
        resp = self.client.post(reverse("partners:supplier_create"), {
            "name": "Nuevo Proveedor",
            "document_number": "20222222222",
            "address": "",
            "phone": "",
            "email": "",
            "contact_name": "",
            "active": True,
        })
        self.assertRedirects(resp, reverse("partners:supplier_list"))
        self.assertTrue(Supplier.objects.filter(document_number="20222222222").exists())

    def test_supplier_duplicate_document(self):
        Supplier.objects.create(company=self.company, name="Existente", document_number="20333333333")
        resp = self.client.post(reverse("partners:supplier_create"), {
            "name": "Otro",
            "document_number": "20333333333",
            "active": True,
        })
        self.assertEqual(resp.status_code, 200)  # stays on form (error)
        self.assertEqual(Supplier.objects.filter(document_number="20333333333").count(), 1)

    # ── Carriers ──────────────────────────────────────────────────────────────

    def test_carrier_list_ok(self):
        Carrier.objects.create(company=self.company, business_name="Trans Rápido", document_number="20444444444")
        resp = self.client.get(reverse("partners:carrier_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Trans Rápido")

    def test_carrier_create_post(self):
        resp = self.client.post(reverse("partners:carrier_create"), {
            "business_name": "Transporte ABC",
            "document_number": "20555555555",
            "license_plate": "ABC-123",
            "driver_name": "Pedro García",
            "driver_license": "Q12345678",
            "phone": "999888777",
            "active": True,
        })
        self.assertRedirects(resp, reverse("partners:carrier_list"))
        self.assertTrue(Carrier.objects.filter(document_number="20555555555").exists())

    def test_carrier_delete(self):
        carrier = Carrier.objects.create(company=self.company, business_name="A Borrar", document_number="20666666666")
        resp = self.client.post(reverse("partners:carrier_delete", args=[carrier.pk]))
        self.assertRedirects(resp, reverse("partners:carrier_list"))
        self.assertFalse(Carrier.objects.filter(pk=carrier.pk).exists())

    # ── Auth guard ────────────────────────────────────────────────────────────

    def test_customer_list_redirects_anonymous(self):
        self.client.logout()
        resp = self.client.get(reverse("partners:customer_list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])
