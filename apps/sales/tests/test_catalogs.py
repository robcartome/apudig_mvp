"""
sales/tests/test_catalogs.py â€” Tests de vistas de catÃ¡logos de ventas.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Store, UserCompanyAccess
from apps.partners.models import DocumentType
from apps.sales.models import DocumentSeries, MeansOfPayment
from apps.treasury.models import Bank, BankAccount
from apps.users.models import UserStore

User = get_user_model()


class CatalogViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="ventas@demo.com", password="test1234")
        self.company = Company.objects.create(name="Empresa Test", ruc="20000000099")
        self.store = Store.objects.create(company=self.company, name="Sucursal 1")
        UserCompanyAccess.objects.create(
            user=self.user,
            company=self.company,
            store=self.store,
        )
        UserStore.objects.create(
            user=self.user,
            store=self.store,
            role="ADMIN",
            is_active=True,
        )
        self.cot_type = DocumentType.objects.create(code="COT", name="CotizaciÃ³n", category="INTERNAL")

        self.client.login(username="ventas@demo.com", password="test1234")
        session = self.client.session
        session["active_company_id"] = str(self.company.id)
        session["active_store_id"] = str(self.store.id)
        session.save()

    # â”€â”€ Series â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
                "document_type": str(self.cot_type.pk),
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
            document_type=self.cot_type,
            series="C001",
        )
        # Intentar duplicado
        resp = self.client.post(
            reverse("sales:series_create"),
            {
                "store": str(self.store.id),
                "document_type": str(self.cot_type.pk),
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
            document_type=self.cot_type,
            series="T001",
            active=True,
        )
        resp = self.client.post(reverse("sales:series_toggle", args=[obj.pk]))
        self.assertRedirects(resp, reverse("sales:series_list"))
        obj.refresh_from_db()
        self.assertFalse(obj.active)

    def test_means_of_payment_form_renders_and_creates_all_required_fields(self):
        bank = Bank.objects.create(company=self.company, name="BCP")
        account = BankAccount.objects.create(
            company=self.company,
            bank=bank,
            name="Cuenta Yape",
            account_number="001-YAPE",
            opening_balance=0,
            opening_balance_date=timezone.localdate(),
        )
        get_response = self.client.get(reverse("sales:means_of_payment_create"))

        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, 'name="kind"')
        self.assertContains(get_response, 'name="requires_reference"')
        self.assertContains(get_response, 'name="bank_account"')

        response = self.client.post(reverse("sales:means_of_payment_create"), {
            "name": "Yape",
            "kind": "DIGITAL_WALLET",
            "bank_account": str(account.pk),
            "requires_reference": "on",
            "active": "on",
        })

        self.assertRedirects(
            response,
            f"{reverse('users:configuracion')}?item=medios_pago",
            fetch_redirect_response=False,
        )
        means = MeansOfPayment.objects.get(company=self.company, name="Yape")
        self.assertEqual(means.kind, MeansOfPayment.Kind.DIGITAL_WALLET)
        self.assertTrue(means.requires_reference)
        self.assertEqual(means.bank_account, account)

    def test_cash_means_cannot_be_linked_to_bank_account(self):
        bank = Bank.objects.create(company=self.company, name="Interbank")
        account = BankAccount.objects.create(
            company=self.company,
            bank=bank,
            name="Cuenta principal",
            account_number="001-CASH",
            opening_balance=0,
            opening_balance_date=timezone.localdate(),
        )

        response = self.client.post(reverse("sales:means_of_payment_create"), {
            "name": "Efectivo banco",
            "kind": "CASH",
            "bank_account": str(account.pk),
            "active": "on",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no debe vincularse a un banco")
        self.assertFalse(MeansOfPayment.objects.filter(name="Efectivo banco").exists())

    # â”€â”€ BusinessDocumentType â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_doctype_list_ok(self):
        resp = self.client.get(reverse("sales:doctype_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Tipos de documento")

    def test_doctype_create_ok(self):
        resp = self.client.post(
            reverse("sales:doctype_create"),
            {
                "code": "FAC",
                "name": "Factura ElectrÃ³nica",
                "category": "SALES",
                "is_sunat": "on",
                "sunat_code": "01",
                "affects_stock": "on",
                "affects_accounting": "on",
                "active": "on",
            },
        )
        self.assertRedirects(resp, reverse("sales:doctype_list"))
        self.assertTrue(DocumentType.objects.filter(code="FAC").exists())

    def test_anonymous_redirect(self):
        self.client.logout()
        resp = self.client.get(reverse("sales:series_list"))
        self.assertEqual(resp.status_code, 302)

    def test_doctype_update_ok(self):
        obj = DocumentType.objects.create(
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

