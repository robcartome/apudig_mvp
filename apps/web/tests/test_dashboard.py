from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.inventory.models import Product, StockByWarehouse, StoreProductConfig, Unit, Warehouse
from apps.partners.models import DocumentType, Supplier
from apps.pos.models import SalesDocumentSource
from apps.purchases.models import PurchaseDocument
from apps.sales.models import SalesDocument
from apps.users.models import Permission, User, UserStore


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class DashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Empresa A", ruc="20111111111")
        cls.other_company = Company.objects.create(name="Empresa B", ruc="20222222222")
        cls.store = Store.objects.create(company=cls.company, name="Principal")
        cls.branch = Store.objects.create(company=cls.company, name="Otra sucursal")
        cls.other_store = Store.objects.create(company=cls.other_company, name="Ajena")
        cls.user = User.objects.create_superuser(email="dashboard@example.test", password="test-password")
        cls.invoice = DocumentType.objects.create(code="01", name="Factura", category="SALES")
        cls.credit = DocumentType.objects.create(code="07", name="Nota de crédito", category="BILLING")
        cls.ticket = DocumentType.objects.create(code="NV", name="Nota de venta", category="INTERNAL")
        cls.unit = Unit.objects.create(code="NIU", name="Unidad")
        cls.warehouse = Warehouse.objects.create(store=cls.store, name="Almacén principal")
        cls.supplier = Supplier.objects.create(company=cls.company, name="Proveedor", document_number="20444444444")

    def setUp(self):
        self.client.force_login(self.user)
        self.select_scope(self.store)
        self.today = timezone.localdate()

    def select_scope(self, store):
        session = self.client.session
        session["active_company_id"] = str(store.company_id)
        session["active_store_id"] = str(store.pk)
        session.save()

    def sale(self, total="100", *, store=None, day=None, **kwargs):
        return SalesDocument.objects.create(
            store=store or self.store,
            document_type=kwargs.pop("document_type", self.invoice),
            issue_date=timezone.make_aware(datetime.combine(day or self.today, time(12))),
            total=Decimal(total), status=kwargs.pop("status", "ISSUED"),
            customer_legal_name=kwargs.pop("customer_legal_name", "Cliente"), **kwargs,
        )

    def product(self, sku, quantity=None, minimum=None, **kwargs):
        product = Product.objects.create(company=self.company, unit=self.unit, name=sku, sku=sku, **kwargs)
        if quantity is not None:
            StockByWarehouse.objects.create(product=product, warehouse=self.warehouse, quantity=quantity)
        if minimum is not None:
            StoreProductConfig.objects.create(store=self.store, product=product, min_stock=minimum)
        return product

    def test_requires_login_and_active_company(self):
        self.client.logout()
        self.assertRedirects(self.client.get(reverse("dashboard")), "/login/?next=/dashboard/", fetch_redirect_response=False)
        self.client.force_login(self.user)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("select_company"), fetch_redirect_response=False)

    def test_empty_dashboard_and_shortcuts_render(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["sales"]["total"], 0)
        self.assertContains(response, "Aún no hay ventas en este período")
        self.assertContains(response, reverse("sales:quotation_create"))
        self.assertNotContains(response, "Próximamente")

    def test_company_without_store_prompts_for_branch(self):
        session = self.client.session
        session.pop("active_store_id")
        session.save()
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Elige una sucursal")
        self.assertNotIn("sales", response.context)

    def test_net_sales_exclude_invalid_statuses_other_scopes_and_currencies(self):
        self.sale("150")
        self.sale("25", document_type=self.credit)
        self.sale("10", status="SUNAT_PENDING")
        for status in ("DRAFT", "VOIDED", "CANCELLED", "SUNAT_REJECTED"):
            self.sale("500", status=status)
        self.sale("900", store=self.branch)
        self.sale("900", store=self.other_store)
        self.sale("800", currency="USD")
        self.sale("700", day=self.today + timedelta(days=1))
        response = self.client.get(reverse("dashboard"), {"period": "today"})
        self.assertEqual(response.context["sales"]["total"], Decimal("135"))
        self.assertEqual(response.context["sales"]["count"], 3)
        self.assertEqual(response.context["sales"]["average"], Decimal("45"))

    def test_consolidated_invoice_does_not_duplicate_original_ticket(self):
        ticket = self.sale("100", document_type=self.ticket)
        invoice = self.sale("100")
        SalesDocumentSource.objects.create(source_document=ticket, target_document=invoice)
        response = self.client.get(reverse("dashboard"), {"period": "today"})
        self.assertEqual(response.context["sales"]["total"], 100)
        self.assertEqual(response.context["sales"]["count"], 1)

    def test_currency_filter_does_not_convert_or_mix_amounts(self):
        self.sale("100")
        self.sale("12.50", currency="USD")
        response = self.client.get(reverse("dashboard"), {"currency": "USD"})
        self.assertEqual(response.context["sales"]["total"], Decimal("12.50"))
        self.assertContains(response, "USD, sin conversión")

    def test_period_comparison_and_missing_days(self):
        self.sale("50", day=self.today - timedelta(days=7))
        self.sale("100")
        response = self.client.get(reverse("dashboard"), {"period": "7d"})
        self.assertEqual(response.context["sales"]["previous"], 50)
        self.assertEqual(response.context["sales"]["change"], 100)
        self.assertEqual(len(response.context["chart"]["series"]), 7)
        self.assertEqual(response.context["chart"]["series"][0]["total"], 0)

    def test_date_boundaries_use_lima_time(self):
        start = timezone.make_aware(datetime.combine(self.today, time.min))
        document = self.sale("20")
        SalesDocument.objects.filter(pk=document.pk).update(issue_date=start)
        document = self.sale("90")
        SalesDocument.objects.filter(pk=document.pk).update(issue_date=start - timedelta(microseconds=1))
        response = self.client.get(reverse("dashboard"), {"period": "today"})
        self.assertEqual(response.context["sales"]["total"], 20)

    def test_negative_net_sales_render_chart_without_division_error(self):
        self.sale("100", document_type=self.credit)
        response = self.client.get(reverse("dashboard"), {"period": "today"})
        self.assertEqual(response.status_code, 200)
        self.assertLess(response.context["chart"]["low"], 0)
        self.assertContains(response, "Ver detalle diario")

    def test_fully_credited_sales_still_show_activity(self):
        self.sale("100")
        self.sale("100", document_type=self.credit)
        response = self.client.get(reverse("dashboard"), {"period": "today"})
        self.assertEqual(response.context["sales"]["total"], 0)
        self.assertContains(response, "Ver detalle diario")
        self.assertNotContains(response, "Aún no hay ventas en este período")

    def test_stock_aggregates_warehouses_and_includes_configured_missing_stock(self):
        product = self.product("SUMADO", "3", 5)
        second = Warehouse.objects.create(store=self.store, name="Segundo")
        StockByWarehouse.objects.create(product=product, warehouse=second, quantity="4")
        self.product("AL-MINIMO", "5", 5)
        self.product("SIN-STOCK", minimum=2)
        self.product("SERVICIO", "0", 5, tracks_inventory=False)
        self.product("INACTIVO", "0", 5, active=False)
        self.product("SIN-CONFIGURACION")
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["stock"]["critical_count"], 2)
        self.assertEqual(response.context["stock"]["count"], 3)
        self.assertEqual({p.sku for p in response.context["stock"]["critical"]}, {"AL-MINIMO", "SIN-STOCK"})

    def test_stock_ignores_other_branches_and_inactive_warehouses(self):
        product = self.product("LOCAL", "0", 2)
        for store, active in ((self.branch, True), (self.store, False), (self.other_store, True)):
            warehouse = Warehouse.objects.create(store=store, name="Fuera del alcance", active=active)
            StockByWarehouse.objects.create(product=product, warehouse=warehouse, quantity="100")
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["stock"]["critical_count"], 1)

    def test_purchase_metric_uses_registered_documents_in_branch_and_currency(self):
        for status, total, currency, store in (
            ("REGISTERED", "70", "PEN", self.store),
            ("DRAFT", "80", "PEN", self.store),
            ("CANCELLED", "90", "PEN", self.store),
            ("REGISTERED", "100", "USD", self.store),
            ("REGISTERED", "110", "PEN", self.branch),
        ):
            PurchaseDocument.objects.create(
                company=self.company, store=store, supplier=self.supplier,
                document_type=self.invoice, issue_date=self.today,
                total=total, document_status=status, currency=currency,
            )
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["purchases"]["total"], 70)
        self.assertEqual(response.context["purchases"]["count"], 1)
        self.assertEqual(response.context["purchases"]["drafts"], 1)

    def test_invalid_filters_fall_back_to_supported_values(self):
        response = self.client.get(reverse("dashboard"), {"period": "bad", "currency": "bad"})
        self.assertEqual(response.context["period"], "month")
        self.assertEqual(response.context["currency"], "PEN")

    def test_restricted_user_does_not_query_or_see_commercial_metrics(self):
        user = User.objects.create_user(email="restricted@example.test", password="test-password")
        UserStore.objects.create(user=user, store=self.store, role="SELLER")
        for module in ("sales.documents", "purchases.documents", "inventory.products"):
            Permission.objects.create(action_name="read", module=module)
        self.client.force_login(user)
        self.select_scope(self.store)
        with patch("apps.web.selectors.get_dashboard_sales") as sales, patch("apps.web.selectors.get_dashboard_purchases") as purchases, patch("apps.web.selectors.get_dashboard_stock") as stock:
            response = self.client.get(reverse("dashboard"))
        sales.assert_not_called()
        purchases.assert_not_called()
        stock.assert_not_called()
        self.assertNotContains(response, "Ventas netas")
        self.assertNotContains(response, "Registrar compra")

    def test_tampered_session_cannot_read_another_company(self):
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.other_store.pk)
        session.save()
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("select_company"), fetch_redirect_response=False)
