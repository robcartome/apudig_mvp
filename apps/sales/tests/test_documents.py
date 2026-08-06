"""
sales/tests/test_sales_documents.py — Tests del módulo de comprobantes.
"""
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.core.models import AuditLog
from apps.inventory.models import (
    Category,
    Movement,
    MovementOrigin,
    MovementStatus,
    Product,
    StockByWarehouse,
    Unit,
    Warehouse,
)
from apps.inventory.selectors import get_movement_traceability_report
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
    update_sales_document_draft,
    void_sales_document,
)
from apps.users.models import Permission, Role, RolePermission, UserRole

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
        self.warehouse = Warehouse.objects.create(
            store=self.store, name="Almacén ventas", is_default=True
        )

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
            register_inventory_movement=False,
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

    def test_inventory_integration_can_be_disabled(self):
        document = self._create_draft()
        self.assertFalse(document.register_inventory_movement)
        self.assertIsNone(document.warehouse)
        self.assertIsNone(document.inventory_movement)

    def test_sale_note_uses_existing_nv_code(self):
        series = DocumentSeries.objects.create(
            company=self.company,
            store=self.store,
            document_type="NV",
            series="NV01",
        )
        document = create_sales_document_draft(
            store_id=str(self.store.id),
            customer=self.customer,
            document_type="NV",
            series=series,
            lines=[_make_line(self.product)],
            issue_date=timezone.now().date(),
        )
        self.assertEqual(document.document_type, "NV")
        self.assertEqual(document.get_document_type_display(), "Nota de Venta")

    def test_server_separates_export_and_free_totals(self):
        export_line = _make_line(self.product, qty="1", price="50")
        export_line["tax_type"] = "40"
        free_line = _make_line(self.product, qty="1", price="30")
        free_line["tax_type"] = "11"
        document = self._create_draft(lines=[export_line, free_line])
        self.assertEqual(document.export_amount, Decimal("50.00"))
        self.assertEqual(document.free_amount, Decimal("30.00"))
        self.assertEqual(document.total, Decimal("50.00"))

    def test_update_is_limited_to_drafts_and_recalculates(self):
        document = self._create_draft()
        updated = update_sales_document_draft(
            document.pk,
            customer=self.customer,
            series=self.fac_series,
            lines=[_make_line(self.product, qty="3", price="10")],
            store_id=str(self.store.pk),
            document_type="01",
            issue_date=timezone.now().date(),
        )
        self.assertEqual(updated.subtotal, Decimal("30.00"))
        issue_sales_document(updated.pk)
        with self.assertRaises(ValueError):
            update_sales_document_draft(
                updated.pk,
                customer=self.customer,
                series=self.fac_series,
                lines=[_make_line(self.product)],
            )

    def test_issue_assigns_number(self):
        v = self._create_draft()
        issued = issue_sales_document(v.pk)
        self.assertEqual(issued.status, "ISSUED")
        self.assertEqual(issued.number, "00000001")
        self.assertEqual(issued.series_code, "F001")
        self.assertTrue(
            AuditLog.objects.filter(
                entity="SalesDocument", entity_id=str(v.pk), action="ISSUE"
            ).exists()
        )

    def test_issue_creates_confirmed_stock_exit(self):
        StockByWarehouse.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=Decimal("10")
        )
        document = create_sales_document_draft(
            store_id=str(self.store.pk),
            customer=self.customer,
            document_type="01",
            series=self.fac_series,
            lines=[_make_line(self.product, qty="2")],
            issue_date=timezone.now().date(),
            warehouse=self.warehouse,
            register_inventory_movement=True,
        )
        issued = issue_sales_document(document.pk)
        stock = StockByWarehouse.objects.get(
            product=self.product, warehouse=self.warehouse
        )
        self.assertEqual(stock.quantity, Decimal("8"))
        self.assertIsNotNone(issued.inventory_movement_id)
        self.assertEqual(issued.inventory_movement.origin, MovementOrigin.SALE)
        self.assertEqual(issued.inventory_movement.status, MovementStatus.CONFIRMED)
        self.assertEqual(issued.inventory_movement.reference_doc, str(document.pk))
        report = get_movement_traceability_report(str(self.store.pk))
        entry = report["products"][0]["entries"][0]
        self.assertEqual(entry["origin"], MovementOrigin.SALE)
        self.assertEqual(entry["sales_document_id"], str(document.pk))

    def test_issue_with_insufficient_stock_rolls_back_number(self):
        StockByWarehouse.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=Decimal("1")
        )
        document = create_sales_document_draft(
            store_id=str(self.store.pk), customer=self.customer, document_type="01",
            series=self.fac_series, lines=[_make_line(self.product, qty="2")],
            issue_date=timezone.now().date(), warehouse=self.warehouse,
            register_inventory_movement=True,
        )
        with self.assertRaisesRegex(ValueError, "Stock insuficiente"):
            issue_sales_document(document.pk)
        document.refresh_from_db()
        self.fac_series.refresh_from_db()
        self.assertEqual(document.status, "DRAFT")
        self.assertEqual(document.number, "")
        self.assertEqual(self.fac_series.current_number, 0)
        self.assertFalse(Movement.objects.exists())

    def test_issue_requires_warehouse_when_stock_control_is_enabled(self):
        document = create_sales_document_draft(
            store_id=str(self.store.pk), customer=self.customer, document_type="01",
            series=self.fac_series, lines=[_make_line(self.product)],
            issue_date=timezone.now().date(), register_inventory_movement=True,
        )
        with self.assertRaisesRegex(ValueError, "seleccionar un almacén"):
            issue_sales_document(document.pk)

    def test_issue_allows_negative_stock_only_when_warehouse_enables_it(self):
        self.warehouse.allow_negative_stock = True
        self.warehouse.save(update_fields=["allow_negative_stock"])
        document = create_sales_document_draft(
            store_id=str(self.store.pk), customer=self.customer, document_type="01",
            series=self.fac_series, lines=[_make_line(self.product, qty="2")],
            issue_date=timezone.now().date(), warehouse=self.warehouse,
            register_inventory_movement=True,
        )
        issue_sales_document(document.pk)
        stock = StockByWarehouse.objects.get(
            product=self.product, warehouse=self.warehouse
        )
        self.assertEqual(stock.quantity, Decimal("-2"))

    def test_non_inventory_product_does_not_create_movement(self):
        self.product.tracks_inventory = False
        self.product.save(update_fields=["tracks_inventory"])
        document = create_sales_document_draft(
            store_id=str(self.store.pk), customer=self.customer, document_type="01",
            series=self.fac_series, lines=[_make_line(self.product)],
            issue_date=timezone.now().date(), warehouse=self.warehouse,
            register_inventory_movement=True,
        )
        issued = issue_sales_document(document.pk)
        self.assertIsNone(issued.inventory_movement)
        self.assertFalse(Movement.objects.exists())

    def test_void_reverses_inventory_exit(self):
        StockByWarehouse.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=Decimal("5")
        )
        document = create_sales_document_draft(
            store_id=str(self.store.pk), customer=self.customer, document_type="01",
            series=self.fac_series, lines=[_make_line(self.product, qty="2")],
            issue_date=timezone.now().date(), warehouse=self.warehouse,
            register_inventory_movement=True,
        )
        issued = issue_sales_document(document.pk)
        void_sales_document(issued.pk, reason="Prueba")
        stock = StockByWarehouse.objects.get(
            product=self.product, warehouse=self.warehouse
        )
        self.assertEqual(stock.quantity, Decimal("5"))
        reversal = issued.inventory_movement.reversal
        self.assertEqual(reversal.origin, MovementOrigin.SALE_REVERSAL)
        self.assertEqual(reversal.status, MovementStatus.CONFIRMED)
        audit = AuditLog.objects.get(
            entity="SalesDocument", entity_id=str(document.pk), action="VOID"
        )
        self.assertEqual(audit.meta_data["inventory_reversal_id"], str(reversal.pk))

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

    def test_issue_rejects_inactive_series_without_consuming_number(self):
        document = self._create_draft()
        self.fac_series.active = False
        self.fac_series.save(update_fields=["active"])
        with self.assertRaisesRegex(ValueError, "serie documental no está activa"):
            issue_sales_document(document.pk)
        self.fac_series.refresh_from_db()
        self.assertEqual(self.fac_series.current_number, 0)

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
            register_inventory_movement=False,
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
        self.assertFalse(note.register_inventory_movement)
        self.assertTrue(
            AuditLog.objects.filter(
                entity_id=str(note.pk), action="CREATE_CREDIT_NOTE"
            ).exists()
        )

    def test_credit_note_requires_issued(self):
        v = self._create_draft()  # still DRAFT
        with self.assertRaises(ValueError):
            create_credit_note(
                sales_document_id=v.pk,
                reason_code="01",
                reason_description="Test",
                series=self.cn_series,
            )

    def test_credit_note_rejects_series_from_another_store(self):
        document = self._create_draft()
        issue_sales_document(document.pk)
        other_store = Store.objects.create(company=self.company, name="Sucursal alterna")
        other_series = DocumentSeries.objects.create(
            company=self.company, store=other_store, document_type="07", series="FC99"
        )
        with self.assertRaisesRegex(ValueError, "no corresponde"):
            create_credit_note(
                sales_document_id=document.pk,
                reason_code="01",
                reason_description="Prueba",
                series=other_series,
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
        self.warehouse = Warehouse.objects.create(
            store=self.store, name="Almacén principal", is_default=True
        )
        self.user = User.objects.create_user(email="vch@demo.com", password="pass1234")
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()

    def _login(self):
        self.client.login(username="vch@demo.com", password="pass1234")

    def _grant_permission(self, action):
        permission = Permission.objects.create(
            code=f"{action}.sales.documents",
            action_name=action,
            module="sales.documents",
        )
        role, _ = Role.objects.get_or_create(name="TEST_SALES")
        RolePermission.objects.create(role=role, permission=permission)
        UserRole.objects.get_or_create(
            user=self.user, role=role, company=self.company
        )
        return permission

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
            register_inventory_movement=False,
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
        self.assertContains(resp, "Documentos de venta")
        self.assertContains(resp, 'name="price_list"')
        self.assertContains(resp, 'name="payment_method"')
        self.assertContains(resp, 'name="means_of_payment"')
        self.assertContains(resp, 'name="seller"')
        self.assertContains(resp, 'name="register_inventory_movement"')
        self.assertContains(resp, 'name="warehouse"')

    def test_configured_permissions_deny_user_without_role(self):
        self._login()
        Permission.objects.create(
            code="read.sales.documents",
            action_name="read",
            module="sales.documents",
        )
        response = self.client.get(reverse("sales:document_list"))
        self.assertEqual(response.status_code, 403)

    def test_read_permission_does_not_allow_document_creation(self):
        self._login()
        self._grant_permission("read")
        Permission.objects.create(
            code="manage.sales.documents",
            action_name="manage",
            module="sales.documents",
        )
        self.assertEqual(
            self.client.get(reverse("sales:document_list")).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("sales:document_create")).status_code, 403
        )

    def test_permission_from_another_company_does_not_grant_access(self):
        self._login()
        permission = Permission.objects.create(
            code="read.sales.documents", action_name="read", module="sales.documents"
        )
        role = Role.objects.create(name="OTHER_COMPANY_READER")
        RolePermission.objects.create(role=role, permission=permission)
        other_company = Company.objects.create(
            name="Empresa sin alcance", ruc="20999999991"
        )
        UserRole.objects.create(user=self.user, role=role, company=other_company)
        self.assertEqual(
            self.client.get(reverse("sales:document_list")).status_code, 403
        )

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
        diagnostics = (
            resp.context["header_form"].errors,
            resp.context["line_formset"].errors,
            [str(message) for message in resp.context["messages"]],
        ) if resp.status_code == 200 else None
        self.assertEqual(
            SalesDocument.objects.filter(store=self.store).count(), 1, diagnostics
        )

    def test_http_cycle_create_issue_and_void_restores_stock_and_audits_actor(self):
        self._login()
        StockByWarehouse.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=Decimal("5")
        )
        data = {
            "store": str(self.store.pk),
            "customer": str(self.customer.pk),
            "document_type": "01",
            "series": str(self.fac_series.pk),
            "issue_date": timezone.now().date().isoformat(),
            "currency": "PEN",
            "register_inventory_movement": "on",
            "warehouse": str(self.warehouse.pk),
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.pk),
            "lines-0-description": "Ciclo integral",
            "lines-0-quantity": "2",
            "lines-0-unit_price": "10",
            "lines-0-discount_amount": "0",
            "lines-0-tax_type": "10",
            "lines-0-igv_rate": "18",
        }
        create_response = self.client.post(reverse("sales:document_create"), data)
        document = SalesDocument.objects.get(store=self.store)
        self.assertEqual(create_response.status_code, 302)

        issue_response = self.client.post(
            reverse("sales:document_issue", kwargs={"pk": document.pk})
        )
        self.assertEqual(issue_response.status_code, 302)
        document.refresh_from_db()
        self.assertEqual(document.status, "ISSUED")
        self.assertEqual(
            StockByWarehouse.objects.get(
                product=self.product, warehouse=self.warehouse
            ).quantity,
            Decimal("3"),
        )

        void_response = self.client.post(
            reverse("sales:document_void", kwargs={"pk": document.pk}),
            {"reason": "Error integral"},
        )
        self.assertEqual(void_response.status_code, 302)
        document.refresh_from_db()
        self.assertEqual(document.status, "VOIDED")
        self.assertEqual(
            StockByWarehouse.objects.get(
                product=self.product, warehouse=self.warehouse
            ).quantity,
            Decimal("5"),
        )
        self.assertEqual(
            set(
                AuditLog.objects.filter(entity_id=str(document.pk)).values_list(
                    "action", flat=True
                )
            ),
            {"CREATE", "ISSUE", "VOID"},
        )
        self.assertFalse(
            AuditLog.objects.filter(entity_id=str(document.pk), user__isnull=True).exists()
        )

    def test_create_requires_warehouse_when_inventory_is_enabled(self):
        self._login()
        data = {
            "store": str(self.store.pk),
            "customer": str(self.customer.pk),
            "document_type": "01",
            "series": str(self.fac_series.pk),
            "issue_date": timezone.now().date().isoformat(),
            "currency": "PEN",
            "register_inventory_movement": "on",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.pk),
            "lines-0-quantity": "1",
            "lines-0-unit_price": "10",
            "lines-0-tax_type": "10",
            "lines-0-igv_rate": "18",
        }
        response = self.client.post(reverse("sales:document_create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("warehouse", response.context["header_form"].errors)
        self.assertFalse(SalesDocument.objects.exists())

    def test_detail_ok(self):
        self._login()
        v = self._create_draft()
        resp = self.client.get(reverse("sales:document_detail", kwargs={"pk": v.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(
            resp, reverse("sales:document_edit", kwargs={"pk": v.pk})
        )
        self.assertContains(resp, "Documento de venta")
        self.assertContains(resp, "Bitácora de auditoría")

    def test_detail_is_isolated_by_active_store(self):
        self._login()
        document = self._create_draft()
        other_store = Store.objects.create(company=self.company, name="Otra sucursal")
        session = self.client.session
        session["active_store_id"] = str(other_store.pk)
        session.save()
        response = self.client.get(
            reverse("sales:document_detail", kwargs={"pk": document.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_edit_draft_updates_lines(self):
        self._login()
        document = self._create_draft()
        data = {
            "store": str(self.store.pk),
            "customer": str(self.customer.pk),
            "document_type": "01",
            "series": str(self.fac_series.pk),
            "issue_date": timezone.now().date().isoformat(),
            "currency": "PEN",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.pk),
            "lines-0-quantity": "4",
            "lines-0-unit_price": "10",
            "lines-0-tax_type": "10",
            "lines-0-igv_rate": "18",
        }
        response = self.client.post(
            reverse("sales:document_edit", kwargs={"pk": document.pk}), data
        )
        if response.status_code == 200:
            self.fail((
                response.context["header_form"].errors,
                response.context["line_formset"].errors,
                [str(message) for message in response.context["messages"]],
            ))
        self.assertRedirects(
            response,
            reverse("sales:document_detail", kwargs={"pk": document.pk}),
            fetch_redirect_response=False,
        )
        document.refresh_from_db()
        self.assertEqual(document.subtotal, Decimal("40.00"))

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
