import json
import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.companies.models import Company, CompanyBranding, Store
from apps.core.models import AuditLog
from apps.inventory.models import (
    Category,
    PriceList,
    Product,
    ProductPrice,
    ProductUnit,
    StockByWarehouse,
    Unit,
    Warehouse,
)
from apps.partners.models import Customer, DocumentType
from apps.pos.models import PosRegister, PosTransaction, SalesDocumentSource
from apps.pos.permissions import POS_PERMISSION_DEFINITIONS, POS_ROLE_ACTIONS
from apps.sales.models import DocumentSeries, MeansOfPayment, PaymentMethod, SalesDocument
from apps.users.models import Permission, Role, RolePermission, User, UserStore


class PosApiTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Ferreteria API",
            ruc="20111112222",
            address="Av. Principal 123",
            phone="999111222",
            email="ventas@ferreteria.test",
        )
        CompanyBranding.objects.create(
            company=self.company,
            pdf_logo_url="https://cdn.example.test/logo-pos.png",
        )
        self.store = Store.objects.create(
            company=self.company,
            name="Tienda principal",
            address="Mostrador principal",
        )
        self.user = User.objects.create_user(email="cashier@pos.test", password="test")
        self._grant_role(self.user, "CASHIER")
        self._activate_context(self.user)

        self.customer = Customer.objects.create(
            company=self.company,
            document_type="6",
            document_number="20666667777",
            legal_name="Cliente POS SAC",
        )
        self.unit = Unit.objects.create(code="NIU", name="Unidad")
        self.product = Product.objects.create(
            company=self.company,
            name="Martillo",
            sku="MAR-001",
            unit=self.unit,
            price_sale=Decimal("100.00"),
            tracks_inventory=True,
        )
        self.warehouse = Warehouse.objects.create(
            store=self.store,
            name="Almacen POS",
            is_default=True,
        )
        StockByWarehouse.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=Decimal("10.000"),
        )
        self.nv_type = DocumentType.objects.create(
            code="NV", name="Nota de Venta", category="INTERNAL"
        )
        self.invoice_type = DocumentType.objects.create(
            code="01", name="Factura", category="BILLING", is_sunat=True, sunat_code="01"
        )
        self.receipt_type = DocumentType.objects.create(
            code="03", name="Boleta", category="BILLING", is_sunat=True, sunat_code="03"
        )
        self.credit_note_type = DocumentType.objects.create(
            code="07", name="Nota de Crédito", category="BILLING", is_sunat=True, sunat_code="07"
        )
        self.debit_note_type = DocumentType.objects.create(
            code="08", name="Nota de Débito", category="BILLING", is_sunat=True, sunat_code="08"
        )
        self.nv_series = self._series(self.nv_type, "NV01")
        self.invoice_series = self._series(self.invoice_type, "F001")
        self.receipt_series = self._series(self.receipt_type, "B001")
        self.credit_note_series = self._series(self.credit_note_type, "BC01")
        self.debit_note_series = self._series(self.debit_note_type, "BD01")
        self.cash = MeansOfPayment.objects.create(
            company=self.company,
            name="Efectivo",
            kind=MeansOfPayment.Kind.CASH,
        )
        self.credit_method = PaymentMethod.objects.create(
            company=self.company,
            name="Credito 30 dias",
            is_cash=False,
            immediate_payment=False,
            is_credit=True,
            credit_days=30,
        )
        self.register = PosRegister.objects.create(
            company=self.company,
            store=self.store,
            code="POS-01",
            name="Caja principal",
            default_warehouse=self.warehouse,
            default_customer=self.customer,
            default_document_type=self.nv_type,
            ticket_series="T01",
        )

    def _series(self, document_type, code):
        return DocumentSeries.objects.create(
            company=self.company,
            store=self.store,
            document_type=document_type,
            series=code,
        )

    def _grant_role(self, user, role_name):
        role, _ = Role.objects.get_or_create(name=role_name)
        codes = POS_ROLE_ACTIONS.get(role_name, set())
        if codes == "*":
            codes = {f"{action}.{module}" for action, module, _ in POS_PERMISSION_DEFINITIONS}
        definitions = {
            f"{action}.{module}": (action, module, description)
            for action, module, description in POS_PERMISSION_DEFINITIONS
        }
        RolePermission.objects.filter(
            role__name__iexact=role_name,
            permission__code__in=definitions,
        ).delete()
        for code in codes:
            action, module, description = definitions[code]
            permission, _ = Permission.objects.update_or_create(
                code=code,
                defaults={
                    "action_name": action,
                    "module": module,
                    "description": description,
                },
            )
            RolePermission.objects.get_or_create(role=role, permission=permission)
        UserStore.objects.update_or_create(
            user=user,
            store=self.store,
            defaults={"role": role_name, "is_active": True},
        )

    def _activate_context(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()

    def _grant_permission(self, role_name, code):
        definitions = {
            f"{action}.{module}": (action, module, description)
            for action, module, description in POS_PERMISSION_DEFINITIONS
        }
        action, module, description = definitions[code]
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "action_name": action,
                "module": module,
                "description": description,
            },
        )
        role = Role.objects.get(name=role_name)
        RolePermission.objects.get_or_create(role=role, permission=permission)

    def _post(self, path, payload):
        return self.client.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _open_session(self, opening="0.00"):
        response = self._post("/api/v1/pos/sessions/open/", {
            "register_id": str(self.register.pk),
            "opening_total": opening,
        })
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["id"]

    def test_expired_session_is_identified_for_pos_client(self):
        self.client.logout()

        response = self.client.get("/api/v1/pos/bootstrap/")

        self.assertIn(response.status_code, (401, 403))
        self.assertEqual(response["X-ApuDig-Auth-Required"], "1")

    def _checkout_payload(self, session_id, *, key=None, unit_price=None):
        line = {
            "product_id": str(self.product.pk),
            "quantity": "1.000",
            "discount_amount": "0.00",
            "tax_type": "10",
            "igv_rate": "18.00",
        }
        if unit_price is not None:
            line["unit_price"] = unit_price
        return {
            "register_id": str(self.register.pk),
            "cash_session_id": session_id,
            "idempotency_key": str(key or uuid.uuid4()),
            "document_type": "NV",
            "series_id": str(self.nv_series.pk),
            "customer_id": str(self.customer.pk),
            "currency": "PEN",
            "lines": [line],
            "payments": [{
                "means_of_payment_id": str(self.cash.pk),
                "amount": "100.00",
                "received_amount": "100.00",
                "change_amount": "0.00",
            }],
        }

    def test_bootstrap_returns_only_active_store_configuration(self):
        response = self.client.get(
            "/api/v1/pos/bootstrap/",
            {"register_id": str(self.register.pk)},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([item["id"] for item in data["registers"]], [str(self.register.pk)])
        self.assertIsNone(data["open_session"])
        self.assertIn("sell.pos", data["permissions"])
        self.assertIn("close.pos.cash", data["permissions"])
        self.assertNotIn("sell.pos.credit", data["permissions"])
        self.assertEqual(data["payment_methods"][0]["id"], str(self.credit_method.pk))
        self.assertEqual(data["readiness"]["registers"], 1)
        self.assertEqual(data["readiness"]["products"], 1)
        self.assertIn("price_lists", data)
        self.assertIn("categories", data)
        self.assertIn("units", data)
        self.assertIn("product_categories", data)
        self.assertEqual(data["suggested_opening_totals"], {"PEN": "0.00", "USD": "0.00"})
        self.assertIn("create.pos.product", data["permissions"])

    def test_product_commercial_detail_returns_prices_and_stock_by_warehouse(self):
        wholesale = PriceList.objects.create(company=self.company, name="Mayorista")
        ProductPrice.objects.create(
            product=self.product, price_list=wholesale,
            amount=Decimal("80.00"), currency="PEN",
        )
        second_store = Store.objects.create(company=self.company, name="Almacén secundario")
        second_warehouse = Warehouse.objects.create(store=second_store, name="Depósito")
        StockByWarehouse.objects.create(
            product=self.product, warehouse=second_warehouse, quantity=Decimal("5.000")
        )

        response = self.client.get(
            f"/api/v1/pos/products/{self.product.pk}/commercial/"
        )

        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["prices"][0]["name"], "Mayorista")
        self.assertEqual(data["prices"][0]["amount"], "80.00")
        self.assertEqual(len(data["warehouses"]), 2)
        self.assertTrue(any(item["is_current"] for item in data["warehouses"]))

    def test_cashier_can_quick_create_product_for_current_company(self):
        category = Category.objects.create(
            company=self.company, code="NUE", name="Nuevos"
        )

        response = self._post("/api/v1/pos/products/create/", {
            "name": "Llave francesa",
            "sku": "lla-001",
            "barcode": "775000000001",
            "unit_id": str(self.unit.pk),
            "category_id": str(category.pk),
            "sale_price": "118.00",
            "includes_tax": True,
            "tax_type": "10",
            "tracks_inventory": True,
        })

        self.assertEqual(response.status_code, 201, response.content)
        product = Product.objects.get(pk=response.json()["id"])
        self.assertEqual(product.company, self.company)
        self.assertEqual(product.sku, "LLA-001")
        self.assertEqual(product.price_sale, Decimal("118.00"))
        self.assertEqual(product.category, category)
        self.assertEqual(product.unit_conversions.get().sale_price, Decimal("118.000000"))
        self.assertTrue(AuditLog.objects.filter(
            entity="Product", entity_id=str(product.pk), meta_data__source="POS"
        ).exists())

    def test_product_catalog_can_be_filtered_by_category(self):
        tools = Category.objects.create(company=self.company, code="HER", name="Herramientas")
        self.product.category = tools
        self.product.save(update_fields=("category",))
        other_category = Category.objects.create(company=self.company, code="PIN", name="Pinturas")

        all_products = self.client.get(
            "/api/v1/pos/products/",
            {"register_id": str(self.register.pk), "search": "", "currency": "PEN"},
        )
        filtered = self.client.get(
            "/api/v1/pos/products/",
            {
                "register_id": str(self.register.pk),
                "category_id": str(other_category.pk),
                "currency": "PEN",
            },
        )

        self.assertEqual(all_products.status_code, 200, all_products.content)
        self.assertEqual([item["id"] for item in all_products.json()], [str(self.product.pk)])
        self.assertEqual(all_products.json()[0]["category"], "Herramientas")
        self.assertEqual(filtered.status_code, 200, filtered.content)
        self.assertEqual(filtered.json(), [])

    def test_price_list_search_requires_permission_and_returns_its_price(self):
        price_list = PriceList.objects.create(company=self.company, name="Mayorista")
        ProductPrice.objects.create(
            product=self.product,
            price_list=price_list,
            amount=Decimal("80.00"),
            currency="PEN",
        )
        params = {
            "register_id": str(self.register.pk),
            "search": "MAR-001",
            "currency": "PEN",
            "price_list_id": str(price_list.pk),
        }

        denied = self.client.get("/api/v1/pos/products/", params)
        self._grant_permission("CASHIER", "change.pos.pricelist")
        allowed = self.client.get("/api/v1/pos/products/", params)

        self.assertEqual(denied.status_code, 403, denied.content)
        self.assertEqual(allowed.status_code, 200, allowed.content)
        self.assertEqual(allowed.json()[0]["unit_price"], "67.796610")

    def test_product_ids_can_reprice_existing_cart_without_text_search(self):
        price_list = PriceList.objects.create(company=self.company, name="Distribuidor")
        ProductPrice.objects.create(
            product=self.product,
            price_list=price_list,
            amount=Decimal("75.00"),
            currency="PEN",
        )
        self._grant_permission("CASHIER", "change.pos.pricelist")

        response = self.client.get("/api/v1/pos/products/", {
            "register_id": str(self.register.pk),
            "product_ids": str(self.product.pk),
            "price_list_id": str(price_list.pk),
            "currency": "PEN",
        })

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([item["id"] for item in response.json()], [str(self.product.pk)])
        self.assertEqual(response.json()[0]["unit_price"], "63.559322")

    def test_product_search_uses_register_price_and_warehouse_stock(self):
        response = self.client.get(
            "/api/v1/pos/products/",
            {
                "register_id": str(self.register.pk),
                "search": "MAR-001",
                "currency": "PEN",
            },
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()), 1)
        product = response.json()[0]
        self.assertEqual(product["id"], str(self.product.pk))
        self.assertEqual(product["unit_price"], "84.745763")
        self.assertEqual(product["stock"], "10.000")
        self.assertEqual(product["unit"], "NIU")

    def test_barcode_search_is_exact_and_does_not_use_text_matching(self):
        self.product.barcode = "7751234567890"
        self.product.save(update_fields=("barcode",))
        Product.objects.create(
            company=self.company,
            name="Referencia 7751234567890 que no debe coincidir",
            sku="REF-001",
            unit=self.unit,
            price_sale=Decimal("50.00"),
            active=True,
        )

        response = self.client.get(
            "/api/v1/pos/products/",
            {
                "register_id": str(self.register.pk),
                "barcode": "7751234567890",
                "currency": "PEN",
            },
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([item["id"] for item in response.json()], [str(self.product.pk)])

    def test_barcode_search_returns_duplicates_for_explicit_selection(self):
        self.product.barcode = "DUPLICADO-01"
        self.product.save(update_fields=("barcode",))
        duplicate = Product.objects.create(
            company=self.company,
            name="Martillo duplicado",
            sku="MAR-002",
            barcode="DUPLICADO-01",
            unit=self.unit,
            price_sale=Decimal("90.00"),
            active=True,
        )

        response = self.client.get(
            "/api/v1/pos/products/",
            {
                "register_id": str(self.register.pk),
                "barcode": "DUPLICADO-01",
            },
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            {item["id"] for item in response.json()},
            {str(self.product.pk), str(duplicate.pk)},
        )

    def test_alternate_unit_uses_presentation_price_and_stock_conversion(self):
        box = Unit.objects.create(code="BX12", name="Caja de 12")
        ProductUnit.objects.create(
            product=self.product,
            unit=box,
            conversion_factor=Decimal("12"),
            sale_price=Decimal("110.00"),
            active=True,
        )
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        stock.quantity = Decimal("24.000")
        stock.save(update_fields=("quantity",))

        search = self.client.get(
            "/api/v1/pos/products/",
            {
                "register_id": str(self.register.pk),
                "search": "MAR-001",
                "currency": "PEN",
            },
        )

        self.assertEqual(search.status_code, 200, search.content)
        product = search.json()[0]
        box_data = next(item for item in product["units"] if item["id"] == str(box.pk))
        self.assertEqual(box_data["conversion_factor"], "12.000000")
        self.assertEqual(box_data["unit_price"], "93.220339")
        self.assertEqual(product["stock_unit"], "NIU")

        session_id = self._open_session()
        payload = self._checkout_payload(session_id)
        payload["lines"][0]["unit_id"] = str(box.pk)
        payload["payments"][0].update({
            "amount": "110.00",
            "received_amount": "110.00",
        })
        checkout = self._post("/api/v1/pos/sales/checkout/", payload)

        self.assertEqual(checkout.status_code, 201, checkout.content)
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, Decimal("12.000"))
        document = SalesDocument.objects.get(pk=checkout.json()["sales_document_id"])
        line = document.lines.get()
        self.assertEqual(line.unit_id, box.pk)
        self.assertEqual(line.conversion_factor, Decimal("12.000000"))
        self.assertEqual(line.stock_quantity, Decimal("12.000000"))

        self._grant_permission("CASHIER", "void.pos.sale")
        voided = self._post(
            f"/api/v1/pos/sales/{checkout.json()['id']}/void/",
            {"reason": "Prueba de reversión por presentación"},
        )
        self.assertEqual(voided.status_code, 200, voided.content)
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, Decimal("24.000"))

    def test_cash_session_summary_reports_expected_cash_before_close(self):
        session_id = self._open_session(opening="10.00")
        checkout = self._post(
            "/api/v1/pos/sales/checkout/",
            self._checkout_payload(session_id),
        )
        self.assertEqual(checkout.status_code, 201, checkout.content)

        response = self.client.get(f"/api/v1/pos/sessions/{session_id}/summary/")

        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["opening_total"], "10.00")
        self.assertEqual(data["cash_sales"], "100.00")
        self.assertEqual(data["expected_cash_total"], "110.00")
        self.assertEqual(data["transactions"]["completed"], 1)
        self.assertTrue(data["can_close"])

    def test_cash_session_summary_includes_sales_and_movement_detail(self):
        session_id = self._open_session(opening="10.00")
        checkout = self._post(
            "/api/v1/pos/sales/checkout/",
            self._checkout_payload(session_id),
        )
        movement = self._post(
            f"/api/v1/pos/sessions/{session_id}/movements/",
            {
                "movement_type": "PAY_IN",
                "amount": "5.00",
                "reason_code": "CHANGE_FUND",
                "description": "Fondo adicional",
            },
        )

        self.assertEqual(checkout.status_code, 201, checkout.content)
        self.assertEqual(movement.status_code, 201, movement.content)
        response = self.client.get(f"/api/v1/pos/sessions/{session_id}/summary/")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["expected_cash_total"], "115.00")
        self.assertEqual(data["sales"][0]["document"], "NV01-00000001")
        self.assertEqual(data["movement_details"][0]["description"], "Fondo adicional")
        self.assertEqual(data["movement_details"][0]["movement_type_label"], "Ingreso")

    def test_withdrawal_requires_specific_authorization_permission(self):
        session_id = self._open_session(opening="100.00")
        payload = {
            "movement_type": "WITHDRAWAL",
            "amount": "20.00",
            "reason_code": "SAFE_WITHDRAWAL",
            "description": "Retiro a boveda",
        }

        denied = self._post(f"/api/v1/pos/sessions/{session_id}/movements/", payload)

        self.assertEqual(denied.status_code, 400, denied.content)
        self.assertEqual(denied.json()["code"], "CASH_MOVEMENT_AUTHORIZATION_REQUIRED")

        self._grant_permission("CASHIER", "authorize.pos.cash_movement")
        allowed = self._post(f"/api/v1/pos/sessions/{session_id}/movements/", payload)

        self.assertEqual(allowed.status_code, 201, allowed.content)
        self.assertEqual(allowed.json()["drawer_cash_after"], "80.00")

    def test_checkout_is_idempotent_and_moves_stock_once(self):
        session_id = self._open_session()
        key = uuid.uuid4()
        payload = self._checkout_payload(session_id, key=key)

        first = self._post("/api/v1/pos/sales/checkout/", payload)
        repeated = self._post("/api/v1/pos/sales/checkout/", payload)

        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(repeated.status_code, 200, repeated.content)
        self.assertTrue(first.json()["created"])
        self.assertFalse(repeated.json()["created"])
        self.assertEqual(first.json()["payment_status"], "PAID")
        self.assertEqual(first.json()["id"], repeated.json()["id"])
        self.assertEqual(SalesDocument.objects.count(), 1)
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal("9.000"))

    def test_checkout_accepts_manual_line_without_inventory_movement(self):
        session_id = self._open_session()
        payload = self._checkout_payload(session_id)
        payload["lines"] = [{
            "line_type": "MANUAL",
            "product_id": None,
            "unit_id": str(self.unit.pk),
            "description": "Flete y descarga especial",
            "product_code": "SIN CODIGO",
            "quantity": "2.000",
            "unit_price": "10.000000",
            "discount_amount": "0.00",
            "tax_type": "10",
            "igv_rate": "18.00",
            "memo": "Entrega en segundo piso",
        }]
        payload["payments"][0].update({
            "amount": "23.60",
            "received_amount": "23.60",
        })

        response = self._post("/api/v1/pos/sales/checkout/", payload)

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["total"], "23.60")
        self.assertTrue(response.json()["lines"][0]["is_manual"])
        document = SalesDocument.objects.get(pk=response.json()["sales_document_id"])
        line = document.lines.select_related("product").get()
        self.assertEqual(line.product.sku, "VARIOS-POS")
        self.assertFalse(line.product.tracks_inventory)
        self.assertEqual(line.product_code, "SIN CODIGO")
        self.assertEqual(line.description, "Flete y descarga especial")
        self.assertEqual(line.memo, "Entrega en segundo piso")
        self.assertFalse(document.inventory_movements.exists())

        search = self.client.get("/api/v1/pos/products/", {
            "register_id": str(self.register.pk),
            "search": "VARIOS-POS",
            "currency": "PEN",
        })
        self.assertEqual(search.status_code, 200, search.content)
        self.assertEqual(search.json(), [])

    def test_stock_failure_rolls_back_document_ticket_and_correlatives(self):
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        stock.quantity = Decimal("0.000")
        stock.save(update_fields=("quantity",))
        session_id = self._open_session()

        response = self._post(
            "/api/v1/pos/sales/checkout/",
            self._checkout_payload(session_id),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "INVALID_POS_SALE")
        self.assertFalse(SalesDocument.objects.exists())
        self.assertFalse(PosTransaction.objects.exists())
        self.register.refresh_from_db()
        self.nv_series.refresh_from_db()
        self.assertEqual(self.register.current_ticket_number, 0)
        self.assertEqual(self.nv_series.current_number, 0)

    def test_cashier_can_override_catalog_price_from_pos(self):
        session_id = self._open_session()
        payload = self._checkout_payload(session_id, unit_price="90.00")
        payload["payments"][0]["amount"] = "106.20"
        payload["payments"][0]["received_amount"] = "106.20"

        response = self._post("/api/v1/pos/sales/checkout/", payload)

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["total"], "106.20")
        self.assertEqual(SalesDocument.objects.get().lines.get().unit_price, Decimal("90.000000"))

    def test_draft_can_be_updated_completed_and_blocks_close_while_pending(self):
        session_id = self._open_session()
        payload = self._checkout_payload(session_id)
        key = payload["idempotency_key"]
        payload["lines"][0]["memo"] = "Color azul, entregar cortado a medida."
        payload["payments"] = []

        created = self._post("/api/v1/pos/sales/drafts/", payload)
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["status"], "DRAFT")
        self.assertEqual(created.json()["idempotency_key"], key)
        self.assertEqual(
            created.json()["lines"][0]["memo"],
            "Color azul, entregar cortado a medida.",
        )
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal("10.000"))

        summary = self.client.get(f"/api/v1/pos/sessions/{session_id}/summary/")
        self.assertEqual(summary.json()["transactions"]["pending"], 1)
        self.assertFalse(summary.json()["can_close"])
        blocked = self._post(f"/api/v1/pos/sessions/{session_id}/close/", {
            "counted_cash_total": "0.00",
            "next_opening_total": "0.00",
        })
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(blocked.json()["code"], "CLOSE_HAS_PENDING_OPERATIONS")

        payload["lines"][0]["quantity"] = "2.000"
        updated = self._post("/api/v1/pos/sales/drafts/", payload)
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.json()["total"], "200.00")
        payload["payments"] = [{
            "means_of_payment_id": str(self.cash.pk),
            "amount": "200.00",
            "received_amount": "200.00",
            "change_amount": "0.00",
        }]
        completed = self._post("/api/v1/pos/sales/checkout/", payload)
        self.assertEqual(completed.status_code, 200, completed.content)
        self.assertEqual(completed.json()["id"], created.json()["id"])
        self.assertEqual(completed.json()["status"], "COMPLETED")
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, Decimal("8.000"))

    def test_draft_can_be_discarded_without_moving_stock(self):
        session_id = self._open_session()
        payload = self._checkout_payload(session_id)
        payload["payments"] = []
        created = self._post("/api/v1/pos/sales/drafts/", payload)

        discarded = self._post(
            f"/api/v1/pos/sales/{created.json()['id']}/cancel-draft/", {}
        )

        self.assertEqual(discarded.status_code, 200, discarded.content)
        self.assertEqual(discarded.json()["status"], "CANCELLED")
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal("10.000"))
        summary = self.client.get(f"/api/v1/pos/sessions/{session_id}/summary/")
        self.assertTrue(summary.json()["can_close"])

    def test_cashier_cannot_register_credit_without_permission(self):
        session_id = self._open_session()
        payload = self._checkout_payload(session_id)
        payload.update({
            "payment_condition": "CREDIT",
            "payment_method_id": str(self.credit_method.pk),
            "due_date": str(timezone.localdate() + timedelta(days=30)),
            "payments": [],
        })

        response = self._post("/api/v1/pos/sales/checkout/", payload)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(SalesDocument.objects.exists())

    def test_credit_sale_can_finish_with_full_outstanding_balance(self):
        self._grant_permission("CASHIER", "sell.pos.credit")
        session_id = self._open_session()
        due_date = timezone.localdate() + timedelta(days=30)
        payload = self._checkout_payload(session_id)
        payload.update({
            "payment_condition": "CREDIT",
            "payment_method_id": str(self.credit_method.pk),
            "due_date": str(due_date),
            "payments": [],
        })

        response = self._post("/api/v1/pos/sales/checkout/", payload)

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["payment_condition"], "CREDIT")
        self.assertEqual(response.json()["payment_status"], "PENDING")
        self.assertEqual(response.json()["paid_amount"], "0.00")
        self.assertEqual(response.json()["outstanding_amount"], "100.00")
        transaction = PosTransaction.objects.get(pk=response.json()["id"])
        self.assertEqual(transaction.sales_document.due_date, due_date)
        self.assertEqual(transaction.sales_document.payment_method, self.credit_method)

    def test_credit_sale_accepts_partial_upfront_payment(self):
        self._grant_permission("CASHIER", "sell.pos.credit")
        session_id = self._open_session()
        payload = self._checkout_payload(session_id)
        payload.update({
            "payment_condition": "CREDIT",
            "payment_method_id": str(self.credit_method.pk),
            "due_date": str(timezone.localdate() + timedelta(days=15)),
        })
        payload["payments"][0].update({
            "amount": "50.00",
            "received_amount": "50.00",
        })

        response = self._post("/api/v1/pos/sales/checkout/", payload)

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["payment_status"], "PARTIAL")
        self.assertEqual(response.json()["paid_amount"], "50.00")
        self.assertEqual(response.json()["outstanding_amount"], "50.00")
        closed = self._post(f"/api/v1/pos/sessions/{session_id}/close/", {
            "counted_cash_total": "50.00",
        })
        self.assertEqual(closed.status_code, 200, closed.content)
        self.assertEqual(closed.json()["expected_cash_total"], "50.00")
        self.assertEqual(closed.json()["cash_difference"], "0.00")

    def test_credit_can_be_collected_in_a_later_cash_session_idempotently(self):
        self._grant_permission("CASHIER", "sell.pos.credit")
        original_session_id = self._open_session()
        payload = self._checkout_payload(original_session_id)
        payload.update({
            "payment_condition": "CREDIT",
            "payment_method_id": str(self.credit_method.pk),
            "due_date": str(timezone.localdate() + timedelta(days=30)),
            "payments": [],
        })
        sale = self._post("/api/v1/pos/sales/checkout/", payload)
        self.assertEqual(sale.status_code, 201, sale.content)
        closed = self._post(f"/api/v1/pos/sessions/{original_session_id}/close/", {
            "counted_cash_total": "0.00",
        })
        self.assertEqual(closed.status_code, 200, closed.content)
        collection_session_id = self._open_session()

        pending = self.client.get(
            f"/api/v1/pos/collections/?cash_session_id={collection_session_id}"
        )
        self.assertEqual(pending.status_code, 200, pending.content)
        self.assertEqual(pending.json()[0]["outstanding_total"], "100.00")

        idempotency_key = uuid.uuid4()
        collection_payload = {
            "sales_document_id": pending.json()[0]["sales_document_id"],
            "cash_session_id": collection_session_id,
            "means_of_payment_id": str(self.cash.pk),
            "amount": "40.00",
            "received_amount": "40.00",
            "idempotency_key": str(idempotency_key),
        }
        first = self._post("/api/v1/pos/collections/", collection_payload)
        repeated = self._post("/api/v1/pos/collections/", collection_payload)

        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(repeated.status_code, 201, repeated.content)
        self.assertEqual(first.json()["outstanding_total"], "60.00")
        transaction_record = PosTransaction.objects.get(pk=sale.json()["id"])
        self.assertEqual(transaction_record.payment_status, PosTransaction.PaymentStatus.PARTIAL)
        payments = transaction_record.sales_document.pos_payments.all()
        self.assertEqual(payments.count(), 1)
        self.assertEqual(payments.get().purpose, "CREDIT_COLLECTION")
        self.assertEqual(str(payments.get().cash_session_id), collection_session_id)
        summary = self.client.get(
            f"/api/v1/pos/sessions/{collection_session_id}/summary/"
        )
        self.assertEqual(summary.json()["expected_cash_total"], "40.00")

    def test_credit_sale_rejects_expired_due_date_atomically(self):
        self._grant_permission("CASHIER", "sell.pos.credit")
        session_id = self._open_session()
        payload = self._checkout_payload(session_id)
        payload.update({
            "payment_condition": "CREDIT",
            "payment_method_id": str(self.credit_method.pk),
            "due_date": str(timezone.localdate() - timedelta(days=1)),
            "payments": [],
        })

        response = self._post("/api/v1/pos/sales/checkout/", payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "INVALID_CREDIT_DUE_DATE")
        self.assertFalse(SalesDocument.objects.exists())
        self.assertFalse(PosTransaction.objects.exists())

    def test_pos_can_issue_invoice_directly_for_ruc_customer(self):
        session_id = self._open_session()
        payload = self._checkout_payload(session_id)
        payload["document_type"] = "01"
        payload["series_id"] = str(self.invoice_series.pk)

        response = self._post("/api/v1/pos/sales/checkout/", payload)

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["document_type"], "01")
        self.assertEqual(response.json()["billing_status"], "INVOICED")
        document = SalesDocument.objects.get(pk=response.json()["sales_document_id"])
        self.assertEqual(document.status, "ISSUED")

    def test_pos_can_issue_receipt_and_reports_pending_electronic_delivery(self):
        session_id = self._open_session()
        payload = self._checkout_payload(session_id)
        payload["document_type"] = "03"
        payload["series_id"] = str(self.receipt_series.pk)

        response = self._post("/api/v1/pos/sales/checkout/", payload)

        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["document_type"], "03")
        self.assertEqual(data["electronic_status"], "PENDING")
        self.assertIsNone(data["qr_payload"])
        self.assertEqual(len(data["lines"]), 1)
        self.assertEqual(data["company_name"], "Ferreteria API")
        self.assertEqual(data["company_ruc"], "20111112222")
        self.assertEqual(data["company_logo_url"], "https://cdn.example.test/logo-pos.png")
        self.assertEqual(data["store_name"], "Tienda principal")
        self.assertTrue(data["document_pdf_url"].endswith("/a4/"))
        a4 = self.client.get(data["document_pdf_url"])
        self.assertEqual(a4.status_code, 200, a4.content)
        self.assertContains(a4, "https://cdn.example.test/logo-pos.png")
        self.assertContains(a4, "Datos de la operación POS")

    def test_sunat_hash_enables_official_qr_payload(self):
        session_id = self._open_session()
        payload = self._checkout_payload(session_id)
        payload["document_type"] = "01"
        payload["series_id"] = str(self.invoice_series.pk)
        checkout = self._post("/api/v1/pos/sales/checkout/", payload)
        document = SalesDocument.objects.get(pk=checkout.json()["sales_document_id"])
        document.sunat_hash = "HASH-FIRMA"
        document.sunat_cdr_status = "ACCEPTED"
        document.save(update_fields=("sunat_hash", "sunat_cdr_status"))

        detail = self.client.get(f"/api/v1/pos/sales/{checkout.json()['id']}/")

        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.json()["electronic_status"], "ACCEPTED")
        self.assertIn("HASH-FIRMA", detail.json()["qr_payload"])
        self.assertTrue(detail.json()["qr_payload"].startswith("20111112222|01|F001|"))

    def test_reprint_is_permission_scoped_and_audited_with_ticket_width(self):
        session_id = self._open_session()
        checkout = self._post(
            "/api/v1/pos/sales/checkout/",
            self._checkout_payload(session_id),
        )

        recent = self.client.get(
            "/api/v1/pos/sales/recent/",
            {"register_id": str(self.register.pk)},
        )
        reprint = self._post(
            f"/api/v1/pos/sales/{checkout.json()['id']}/reprint/",
            {"width": "58"},
        )

        self.assertEqual(recent.status_code, 200, recent.content)
        self.assertEqual([item["id"] for item in recent.json()], [checkout.json()["id"]])
        self.assertEqual(reprint.status_code, 200, reprint.content)
        self.assertEqual(reprint.json()["print_width"], "58")
        audit = AuditLog.objects.get(
            action="REPRINT",
            entity="PosTransaction",
            entity_id=checkout.json()["id"],
        )
        self.assertEqual(audit.meta_data["width_mm"], "58")

    def test_reprint_rejects_unsupported_ticket_width(self):
        session_id = self._open_session()
        checkout = self._post(
            "/api/v1/pos/sales/checkout/",
            self._checkout_payload(session_id),
        )

        response = self._post(
            f"/api/v1/pos/sales/{checkout.json()['id']}/reprint/",
            {"width": "72"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(AuditLog.objects.filter(action="REPRINT").exists())

    def test_partial_return_restores_stock_and_reduces_expected_cash(self):
        self._grant_permission("CASHIER", "refund.pos.sale")
        session_id = self._open_session()
        checkout = self._post(
            "/api/v1/pos/sales/checkout/",
            self._checkout_payload(session_id),
        )
        line_id = checkout.json()["lines"][0]["id"]
        return_key = uuid.uuid4()
        payload = {
            "cash_session_id": session_id,
            "idempotency_key": str(return_key),
            "reason": "Producto no requerido",
            "refund_means_of_payment_id": str(self.cash.pk),
            "lines": [{"line_id": line_id, "quantity": "0.5000"}],
        }

        returned = self._post(
            f"/api/v1/pos/sales/{checkout.json()['id']}/return/",
            payload,
        )
        repeated = self._post(
            f"/api/v1/pos/sales/{checkout.json()['id']}/return/",
            payload,
        )

        self.assertEqual(returned.status_code, 201, returned.content)
        self.assertEqual(repeated.status_code, 200, repeated.content)
        self.assertTrue(returned.json()["created"])
        self.assertFalse(repeated.json()["created"])
        self.assertEqual(returned.json()["total"], "50.00")
        self.assertIsNone(returned.json()["credit_note_id"])
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal("9.500"))
        summary = self.client.get(f"/api/v1/pos/sessions/{session_id}/summary/")
        self.assertEqual(summary.json()["refund_total"], "50.00")
        self.assertEqual(summary.json()["expected_cash_total"], "50.00")

    def test_cashier_cannot_return_without_refund_permission(self):
        session_id = self._open_session()
        checkout = self._post(
            "/api/v1/pos/sales/checkout/",
            self._checkout_payload(session_id),
        )

        response = self._post(
            f"/api/v1/pos/sales/{checkout.json()['id']}/return/",
            {
                "cash_session_id": session_id,
                "idempotency_key": str(uuid.uuid4()),
                "reason": "Intento no autorizado",
                "refund_means_of_payment_id": str(self.cash.pk),
                "lines": [{
                    "line_id": checkout.json()["lines"][0]["id"],
                    "quantity": "1.0000",
                }],
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_cash_refund_requires_sufficient_expected_cash(self):
        self._grant_permission("CASHIER", "refund.pos.sale")
        original_session_id = self._open_session()
        checkout = self._post(
            "/api/v1/pos/sales/checkout/",
            self._checkout_payload(original_session_id),
        )
        closed = self._post(f"/api/v1/pos/sessions/{original_session_id}/close/", {
            "counted_cash_total": "100.00",
        })
        self.assertEqual(closed.status_code, 200, closed.content)
        refund_session_id = self._open_session()

        response = self._post(
            f"/api/v1/pos/sales/{checkout.json()['id']}/return/",
            {
                "cash_session_id": refund_session_id,
                "idempotency_key": str(uuid.uuid4()),
                "reason": "Caja sin fondos",
                "refund_means_of_payment_id": str(self.cash.pk),
                "lines": [{
                    "line_id": checkout.json()["lines"][0]["id"],
                    "quantity": "1.0000",
                }],
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "INSUFFICIENT_CASH_FOR_REFUND")
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal("9.000"))

    def test_fiscal_return_issues_credit_note_and_prevents_excess_return(self):
        self._grant_permission("CASHIER", "refund.pos.sale")
        session_id = self._open_session()
        payload = self._checkout_payload(session_id)
        payload["document_type"] = "01"
        payload["series_id"] = str(self.invoice_series.pk)
        checkout = self._post("/api/v1/pos/sales/checkout/", payload)
        line_id = checkout.json()["lines"][0]["id"]
        return_payload = {
            "cash_session_id": session_id,
            "idempotency_key": str(uuid.uuid4()),
            "credit_note_series_id": str(self.credit_note_series.pk),
            "reason_code": "01",
            "reason": "Devolución total",
            "refund_means_of_payment_id": str(self.cash.pk),
            "lines": [{"line_id": line_id, "quantity": "1.0000"}],
        }

        returned = self._post(
            f"/api/v1/pos/sales/{checkout.json()['id']}/return/",
            return_payload,
        )

        self.assertEqual(returned.status_code, 201, returned.content)
        note = SalesDocument.objects.get(pk=returned.json()["credit_note_id"])
        self.assertEqual(note.document_type.code, "07")
        self.assertEqual(note.status, "ISSUED")
        self.assertEqual(str(note.reference_document_id), checkout.json()["sales_document_id"])
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal("10.000"))

        return_payload["idempotency_key"] = str(uuid.uuid4())
        excessive = self._post(
            f"/api/v1/pos/sales/{checkout.json()['id']}/return/",
            return_payload,
        )
        self.assertEqual(excessive.status_code, 400)
        self.assertEqual(excessive.json()["code"], "RETURN_QUANTITY_EXCEEDED")

    def test_debit_note_is_related_and_does_not_move_stock(self):
        session_id = self._open_session()
        payload = self._checkout_payload(session_id)
        payload["document_type"] = "01"
        payload["series_id"] = str(self.invoice_series.pk)
        checkout = self._post("/api/v1/pos/sales/checkout/", payload)
        line_id = checkout.json()["lines"][0]["id"]

        debit_key = str(uuid.uuid4())
        debit_payload = {
                "idempotency_key": debit_key,
                "series_id": str(self.debit_note_series.pk),
                "reason_code": "01",
                "reason": "Interés por mora",
                "lines": [{
                    "line_id": line_id,
                    "description": "Interés por mora",
                    "quantity": "1.0000",
                    "unit_price": "10.000000",
                }],
            }
        response = self._post(
            f"/api/v1/pos/sales/{checkout.json()['id']}/debit-note/",
            debit_payload,
        )
        repeated = self._post(
            f"/api/v1/pos/sales/{checkout.json()['id']}/debit-note/",
            debit_payload,
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(repeated.status_code, 200, repeated.content)
        self.assertFalse(repeated.json()["created"])
        note = SalesDocument.objects.get(pk=response.json()["id"])
        self.assertEqual(note.document_type.code, "08")
        self.assertEqual(str(note.reference_document_id), checkout.json()["sales_document_id"])
        self.assertFalse(note.register_inventory_movement)
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal("9.000"))

    def test_cashier_cannot_void_sale_without_specific_permission(self):
        session_id = self._open_session()
        checkout = self._post(
            "/api/v1/pos/sales/checkout/",
            self._checkout_payload(session_id),
        )
        self.assertEqual(checkout.status_code, 201, checkout.content)

        response = self._post(
            f"/api/v1/pos/sales/{checkout.json()['id']}/void/",
            {"reason": "Prueba"},
        )

        self.assertEqual(response.status_code, 403)

    def test_user_without_sell_permission_is_rejected(self):
        user = User.objects.create_user(email="warehouse@pos.test", password="test")
        self._grant_role(user, "WAREHOUSE")
        self._activate_context(user)

        response = self._post("/api/v1/pos/sales/checkout/", {
            "register_id": str(self.register.pk),
        })

        self.assertEqual(response.status_code, 403)

    def test_cross_tenant_register_is_not_exposed(self):
        other_company = Company.objects.create(name="Otra compania", ruc="20999998888")
        other_store = Store.objects.create(company=other_company, name="Sucursal ajena")
        foreign_register = PosRegister.objects.create(
            company=other_company,
            store=other_store,
            code="OTHER",
            name="Caja ajena",
        )

        response = self._post("/api/v1/pos/sessions/open/", {
            "register_id": str(foreign_register.pk),
            "opening_total": "0.00",
        })

        self.assertEqual(response.status_code, 404)

    def test_quick_customer_creation_is_company_scoped_and_idempotent(self):
        payload = {
            "document_type": "1",
            "document_number": "44556677",
            "legal_name": "Cliente Mostrador",
            "address": "Av. Principal 123",
        }

        created = self._post("/api/v1/pos/customers/", payload)
        repeated = self._post("/api/v1/pos/customers/", payload)

        self.assertEqual(created.status_code, 201)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(created.json()["id"], repeated.json()["id"])
        self.assertEqual(Customer.objects.filter(company=self.company).count(), 2)

    def test_pending_tickets_are_consolidated_before_cash_close_without_double_stock(self):
        session_id = self._open_session()
        first = self._post(
            "/api/v1/pos/sales/checkout/",
            self._checkout_payload(session_id),
        )
        second = self._post(
            "/api/v1/pos/sales/checkout/",
            self._checkout_payload(session_id),
        )
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 201, second.content)
        source_ids = [
            first.json()["sales_document_id"],
            second.json()["sales_document_id"],
        ]

        request_response = self._post("/api/v1/pos/invoice-requests/", {
            "source_document_ids": source_ids,
        })
        self.assertEqual(request_response.status_code, 200, request_response.content)

        blocked_close = self._post(f"/api/v1/pos/sessions/{session_id}/close/", {
            "counted_cash_total": "200.00",
        })
        self.assertEqual(blocked_close.status_code, 400)
        self.assertEqual(blocked_close.json()["code"], "CLOSE_HAS_PENDING_INVOICES")

        invoice_response = self._post("/api/v1/pos/consolidated-invoices/", {
            "source_document_ids": source_ids,
            "invoice_series_id": str(self.invoice_series.pk),
        })
        self.assertEqual(invoice_response.status_code, 201, invoice_response.content)
        self.assertEqual(invoice_response.json()["total"], "200.00")
        self.assertEqual(SalesDocumentSource.objects.count(), 2)

        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal("8.000"))

        closed = self._post(f"/api/v1/pos/sessions/{session_id}/close/", {
            "counted_cash_total": "200.00",
        })
        self.assertEqual(closed.status_code, 200, closed.content)
        self.assertEqual(closed.json()["cash_difference"], "0.00")
