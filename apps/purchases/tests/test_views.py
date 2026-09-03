from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.companies.models import Company, CompanyOperationalSettings, Store
from apps.inventory.models import Product, ProductUnit, Unit, Warehouse
from apps.partners.models import DocumentType, Supplier
from apps.purchases.models import PurchaseCategory, PurchaseDocument
from apps.sales.models import PaymentMethod


class PurchaseDocumentViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(name="Empresa vistas compras", ruc="20611111111")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.other_store = Store.objects.create(company=self.company, name="Secundaria")
        self.warehouse = Warehouse.objects.create(store=self.store, name="Almacén principal")
        self.other_warehouse = Warehouse.objects.create(store=self.other_store, name="Almacén secundario")
        self.supplier = Supplier.objects.create(company=self.company, name="Proveedor vista", document_number="20622222222")
        self.document_type = DocumentType.objects.create(code="FC-V", name="Factura compra vista", category="BILLING")
        self.unit = Unit.objects.create(code="UCV", name="Unidad compras vista")
        self.product = Product.objects.create(company=self.company, name="Producto vista", sku="PCV-1", unit=self.unit)
        self.user = get_user_model().objects.create_user(email="compras@example.com", password="testpass")
        self.client.login(username="compras@example.com", password="testpass")
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()

    def payload(self):
        return {
            "supplier": str(self.supplier.pk), "document_type": str(self.document_type.pk), "series": "F001", "number": "99", "issue_date": date(2026, 9, 1).isoformat(), "currency": "PEN", "exchange_rate": "1",
            "lines-TOTAL_FORMS": "1", "lines-INITIAL_FORMS": "0", "lines-MIN_NUM_FORMS": "1", "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.pk), "lines-0-description": "Producto facturado", "lines-0-unit": str(self.unit.pk), "lines-0-quantity": "2", "lines-0-unit_price": "10", "lines-0-discount_amount": "0", "lines-0-tax_type": "10", "lines-0-igv_rate": "18", "lines-0-update_purchase_price": "on",
        }

    def test_create_detail_register_cycle_without_inventory(self):
        response = self.client.post(reverse("purchases:document_create"), self.payload())
        if response.status_code == 200:
            self.fail((response.context["form"].errors, response.context["formset"].errors))
        document = PurchaseDocument.objects.get()
        self.assertRedirects(response, reverse("purchases:document_list"), fetch_redirect_response=False)
        self.assertFalse(document.register_inventory_movement)
        response = self.client.post(reverse("purchases:document_register", args=[document.pk]))
        self.assertRedirects(response, reverse("purchases:document_list"), fetch_redirect_response=False)
        document.refresh_from_db()
        self.assertEqual(document.document_status, "REGISTERED")

    def test_edit_populates_dates_and_product_code(self):
        self.client.post(reverse("purchases:document_create"), self.payload())
        document = PurchaseDocument.objects.get()

        response = self.client.get(reverse("purchases:document_edit", args=[document.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="2026-09-01"', html=False)
        self.assertContains(response, f"{self.product.sku} | {self.product.name}")

    def test_cash_condition_sets_same_day_due_date_without_marking_unregistered_payment_as_paid(self):
        cash = PaymentMethod.objects.create(company=self.company, name="Contado", is_cash=True)
        payload = self.payload()
        payload.update({"number": "102", "payment_method": str(cash.pk), "due_date": "2026-09-20"})

        response = self.client.post(reverse("purchases:document_create"), payload)

        self.assertRedirects(response, reverse("purchases:document_list"), fetch_redirect_response=False)
        document = PurchaseDocument.objects.get(number="102")
        self.assertEqual(document.due_date, document.issue_date)
        self.assertEqual(document.payment_status, "UNPAID")

    def test_credit_condition_requires_due_date_and_preserves_foreign_currency_rate(self):
        credit = PaymentMethod.objects.create(company=self.company, name="Credito 30 dias", is_cash=False)
        payload = self.payload()
        payload.update({
            "number": "103", "payment_method": str(credit.pk), "due_date": "",
            "currency": "USD", "exchange_rate": "3.75",
        })
        response = self.client.post(reverse("purchases:document_create"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "fecha de vencimiento")

        payload["due_date"] = "2026-10-01"
        response = self.client.post(reverse("purchases:document_create"), payload)
        self.assertRedirects(response, reverse("purchases:document_list"), fetch_redirect_response=False)
        document = PurchaseDocument.objects.get(number="103")
        self.assertEqual(document.currency, "USD")
        self.assertEqual(document.exchange_rate, Decimal("3.750000"))

    def test_detail_is_isolated_by_active_store(self):
        response = self.client.post(reverse("purchases:document_create"), self.payload())
        if response.status_code == 200:
            self.fail((response.context["form"].errors, response.context["formset"].errors))
        document = PurchaseDocument.objects.get()
        session = self.client.session
        session["active_store_id"] = str(self.other_store.pk)
        session.save()
        self.assertEqual(self.client.get(reverse("purchases:document_detail", args=[document.pk])).status_code, 404)

    def test_list_and_preview_include_purchase_document_details(self):
        self.client.post(reverse("purchases:document_create"), self.payload())
        document = PurchaseDocument.objects.get()

        response = self.client.get(reverse("purchases:document_list"))
        self.assertContains(response, "Fecha de creación")
        self.assertContains(response, "Fecha de emisión")
        self.assertContains(response, "Fecha de vencimiento")
        self.assertContains(response, "Estado de pago")
        self.assertContains(response, "Operaciones")
        self.assertContains(response, reverse("purchases:document_preview", args=[document.pk]))
        self.assertContains(response, reverse("purchases:document_edit", args=[document.pk]))
        self.assertContains(response, reverse("purchases:document_register", args=[document.pk]))
        self.assertContains(response, reverse("purchases:document_delete", args=[document.pk]))
        self.assertNotContains(response, reverse("purchases:payment_create", args=[document.pk]))
        self.assertNotContains(response, reverse("purchases:document_cancel", args=[document.pk]))

        response = self.client.get(reverse("purchases:document_preview", args=[document.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.supplier.name)
        self.assertContains(response, self.product.name)

    def test_anonymous_list_redirects_to_login(self):
        self.client.logout()
        response = self.client.get(reverse("purchases:document_list"))
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)

    def test_purchase_form_includes_invoice_type_catalogued_as_sales(self):
        invoice = DocumentType.objects.create(
            code="01-PV", name="Factura comercial", category="SALES"
        )
        response = self.client.get(reverse("purchases:document_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'value="{invoice.pk}"')
        self.assertContains(response, invoice.name)
        self.assertContains(response, 'class="partner-select w-100"')
        self.assertContains(response, 'class="product-select w-100"')
        self.assertContains(response, 'name="lines-0-description"', html=False)
        self.assertContains(response, 'type="hidden" name="lines-0-description"', html=False)
        self.assertContains(response, "Bien o Servicio")
        self.assertContains(response, "Valor Unit.")
        self.assertContains(response, "Precio Unit.")
        self.assertNotContains(response, 'name="lines-0-purchase_category"', html=False)
        self.assertContains(response, 'class="form-control form-control-sm text-end quantity-input"', html=False)
        self.assertContains(response, 'inputmode="decimal"', html=False)
        self.assertContains(response, 'id="summary-total"', html=False)

    def test_purchase_form_uses_company_price_decimals_and_default_igv(self):
        CompanyOperationalSettings.objects.update_or_create(
            company=self.company,
            defaults={"price_decimal_places": 3, "default_igv_rate": Decimal("15.50")},
        )

        response = self.client.get(reverse("purchases:document_create"))

        self.assertContains(response, 'data-price-decimals="3"', html=False)
        self.assertContains(response, 'data-igv-rate="15.50"', html=False)
        self.assertEqual(response.context["formset"].forms[0].fields["igv_rate"].initial, Decimal("15.50"))

    def test_purchase_form_only_lists_active_store_warehouses_and_saves_selected_one(self):
        response = self.client.get(reverse("purchases:document_create"))
        self.assertContains(response, self.warehouse.name)
        self.assertNotContains(response, self.other_warehouse.name)

        payload = self.payload()
        payload.update({
            "number": "101",
            "register_inventory_movement": "on",
            "warehouse": str(self.warehouse.pk),
        })
        response = self.client.post(reverse("purchases:document_create"), payload)
        if response.status_code == 200:
            self.fail((response.context["form"].errors, response.context["formset"].errors))
        self.assertEqual(PurchaseDocument.objects.get(number="101").warehouse, self.warehouse)

    def test_invalid_purchase_displays_line_errors_instead_of_template_code(self):
        payload = self.payload()
        payload["lines-0-quantity"] = ""
        response = self.client.post(reverse("purchases:document_create"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Revisa la informaci")
        self.assertContains(response, "Cantidad")
        self.assertNotContains(response, '{% include "components/form_errors_alert.html"')

    def test_product_search_returns_principal_unit_first(self):
        bag = Unit.objects.create(code="BGV", name="Bolsa vista")
        ProductUnit.objects.create(
            product=self.product, unit=bag, conversion_factor=10,
            purchase_price=100,
        )
        response = self.client.get(reverse("inventory:api_product_search"), {"q": "Producto vista"})
        self.assertEqual(response.status_code, 200)
        product = response.json()["products"][0]
        self.assertEqual(product["unit_id"], str(self.unit.pk))
        self.assertEqual(product["units"][0]["id"], str(self.unit.pk))

    def test_price_history_view_is_available(self):
        response = self.client.get(reverse("purchases:price_history"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Historico de precios de compra")

    def test_create_expense_line_with_purchase_category(self):
        category = PurchaseCategory.objects.create(
            company=self.company, code="ALQ", name="Alquileres"
        )
        payload = self.payload()
        payload.update({
            "number": "100",
            "lines-0-product": "",
            "lines-0-purchase_category": str(category.pk),
            "lines-0-unit": "",
            "lines-0-description": "Alquiler del local",
        })
        form_response = self.client.get(reverse("purchases:expense_create"))
        self.assertContains(form_response, 'class="partner-select w-100"', html=False)
        self.assertContains(form_response, category.name)
        self.assertContains(form_response, 'id="expense-summary-total"', html=False)
        response = self.client.post(reverse("purchases:expense_create"), payload)
        if response.status_code == 200:
            self.fail((response.context["form"].errors, response.context["formset"].errors))
        document = PurchaseDocument.objects.get()
        self.assertEqual(document.lines.get().purchase_category, category)
        self.assertFalse(document.register_inventory_movement)
        self.assertRedirects(
            self.client.get(reverse("purchases:document_edit", args=[document.pk])),
            reverse("purchases:expense_edit", args=[document.pk]),
            fetch_redirect_response=False,
        )
