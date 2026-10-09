import json

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from apps.companies.models import Company, CompanyOperationalSettings, Store
from apps.inventory.models import Unit, Warehouse
from apps.partners.models import Customer, DocumentType
from apps.pos.models import PosRegister
from apps.pos.permissions import POS_PERMISSION_DEFINITIONS
from apps.users.models import Permission, Role, RolePermission, User, UserStore


class PosWorkspaceViewTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Ferreteria Web", ruc="20123456789")
        self.store = Store.objects.create(company=self.company, name="Tienda principal")
        self.user = User.objects.create_user(email="cashier-web@pos.test", password="test")
        self.role, _ = Role.objects.get_or_create(name="CASHIER")
        action, module, description = next(
            item for item in POS_PERMISSION_DEFINITIONS if f"{item[0]}.{item[1]}" == "read.pos"
        )
        permission, _ = Permission.objects.update_or_create(
            code="read.pos",
            defaults={
                "action_name": action,
                "module": module,
                "description": description,
            },
        )
        RolePermission.objects.create(role=self.role, permission=permission)
        UserStore.objects.create(
            user=self.user,
            store=self.store,
            role=self.role.name,
            is_active=True,
        )

    def activate_context(self):
        self.client.force_login(self.user)
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()

    def test_workspace_requires_login(self):
        response = self.client.get("/pos/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/pos/login/?next=/pos/")

    def test_login_returns_to_installed_pos_start_url(self):
        response = self.client.post(
            "/pos/login/?next=/pos/",
            {"username": self.user.email, "password": "test", "next": "/pos/"},
        )

        self.assertRedirects(response, "/pos/", fetch_redirect_response=False)

    def test_pos_context_route_keeps_anonymous_user_inside_pwa_scope(self):
        response = self.client.get(reverse("pos:select_context"))

        self.assertRedirects(
            response,
            "/pos/login/?next=/pos/contexto/",
            fetch_redirect_response=False,
        )

    def test_workspace_without_active_context_preserves_pos_destination(self):
        self.client.force_login(self.user)

        response = self.client.get("/pos/")

        self.assertRedirects(
            response,
            "/pos/contexto/?next=%2Fpos%2F",
            fetch_redirect_response=False,
        )

    def test_workspace_renders_for_cashier_with_read_permission(self):
        self.activate_context()

        response = self.client.get("/pos/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "pos/sale.html")
        self.assertContains(response, "Nueva venta")
        self.assertContains(response, 'id="quick-new-sale"')
        self.assertContains(response, "Alt+N")
        self.assertContains(response, 'id="open-close-session"')
        self.assertContains(response, 'id="quick-close-session"')
        self.assertContains(response, "/api/v1/pos/sales/checkout/")
        self.assertContains(response, 'id="checkout-review-dialog"')
        self.assertContains(response, "Esta es una precuenta")
        self.assertContains(response, "Confirmar y cobrar")
        self.assertContains(response, 'id="receipt-result-title"')
        self.assertContains(response, 'id="receipt-result-message"')
        self.assertContains(response, 'id="continue-draft-button"')
        self.assertContains(response, 'id="add-manual-line"')
        self.assertNotContains(response, 'id="manual-line-dialog"')
        self.assertContains(response, 'data-product-search-mode="SEARCH"')
        self.assertContains(response, 'id="pos-catalog-browser" class="pos-catalog-browser" hidden')
        self.assertContains(response, 'id="mobile-checkout-button"')
        self.assertContains(response, 'aria-controls="checkout-panel"')
        self.assertContains(response, 'aria-expanded="false"')
        self.assertContains(response, 'rel="manifest"')
        self.assertContains(response, reverse("pos:manifest"))
        self.assertContains(response, 'id="pos-network-status"')
        self.assertContains(response, 'id="scan-barcode"')
        self.assertContains(response, 'aria-label="Escanear código de barras con la cámara"')
        self.assertContains(response, 'id="barcode-scanner-dialog"')
        self.assertContains(response, 'id="barcode-scanner-video"')
        self.assertContains(response, "vendor/zxing/zxing-browser-0.2.1.min.js")
        self.assertContains(response, "js/pos-barcode-scanner.js")

    def test_pos_manifest_exposes_install_metadata_and_icons(self):
        response = self.client.get(reverse("pos:manifest"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/manifest+json")
        manifest = json.loads(response.content)
        self.assertEqual(manifest["start_url"], "/pos/")
        self.assertEqual(manifest["scope"], "/pos/")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual([icon["sizes"] for icon in manifest["icons"]], ["192x192", "512x512"])
        self.assertIsNotNone(finders.find("pwa/pos-icon-192.png"))
        self.assertIsNotNone(finders.find("pwa/pos-icon-512.png"))

    def test_pos_service_worker_is_public_and_limited_to_pos_scope(self):
        response = self.client.get(reverse("pos:service_worker"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/javascript"))
        self.assertEqual(response["Service-Worker-Allowed"], "/pos/")
        self.assertIn("no-cache", response["Cache-Control"])
        self.assertContains(response, "apudig-pos-static-v16")
        self.assertContains(response, "/static/js/pos.js?v=20261009-3")
        self.assertContains(response, "ApuDig POS necesita")
        self.assertNotContains(response, "'/api/")

    def test_pos_javascript_exposes_decoupled_scanner_hook(self):
        script_path = finders.find("js/pos.js")

        self.assertIsNotNone(script_path)
        with open(script_path, encoding="utf-8") as script_file:
            script = script_file.read()
        self.assertIn('new CustomEvent("pos:scan-requested"', script)
        self.assertIn('barcodeField: "barcode"', script)

    def test_pos_javascript_opens_draft_receipt_and_discounts_final_total(self):
        script_path = finders.find("js/pos.js")

        with open(script_path, encoding="utf-8") as script_file:
            script = script_file.read()
        self.assertIn('openDialog(byId("success-dialog"))', script)
        self.assertIn('global_discount_before_tax: false', script)
        self.assertIn('const factor = discountedTotal / result.total', script)
        self.assertIn('value="percent"', script)
        self.assertIn('data-action="discount-toggle"', script)
        self.assertIn('Borrador reservado', script)
        self.assertIn('Próximo N.º', script)
        self.assertIn('pos-receipt__internal-reference', script)
        self.assertIn('Ref. interna POS:', script)
        self.assertIn('BORRADOR · NO ES COMPROBANTE DE PAGO.', script)
        self.assertNotIn('<small>Ticket ', script)

    def test_pos_javascript_keeps_draft_when_starting_new_sale_and_toggles_cash_action(self):
        script_path = finders.find("js/pos.js")

        with open(script_path, encoding="utf-8") as script_file:
            script = script_file.read()
        self.assertIn("function startNewSale()", script)
        self.assertIn("El borrador guardado no se modificará", script)
        self.assertIn("function handleCashSessionAction()", script)
        self.assertIn("state.session ? 'Cerrar caja' : 'Abrir caja'", script)
        self.assertIn("hasPermission('open.pos.cash')", script)

    def test_pos_success_alerts_auto_hide_but_errors_remain_visible(self):
        script_path = finders.find("js/pos.js")

        with open(script_path, encoding="utf-8") as script_file:
            script = script_file.read()
        self.assertIn("if (kind === 'success')", script)
        self.assertIn("window.setTimeout(hideAlert, 5000)", script)
        self.assertNotIn("if (kind === 'error')", script)

    def test_barcode_scanner_releases_camera_and_uses_local_zxing(self):
        scanner_path = finders.find("js/pos-barcode-scanner.js")
        zxing_path = finders.find("vendor/zxing/zxing-browser-0.2.1.min.js")
        license_path = finders.find("vendor/zxing/LICENSE")

        self.assertIsNotNone(scanner_path)
        self.assertIsNotNone(zxing_path)
        self.assertIsNotNone(license_path)
        with open(scanner_path, encoding="utf-8") as scanner_file:
            scanner = scanner_file.read()
        self.assertIn('facingMode: { ideal: "environment" }', scanner)
        self.assertIn("track.stop()", scanner)
        self.assertIn('window.addEventListener("pagehide", stopScanner)', scanner)
        self.assertIn('new CustomEvent("pos:barcode-detected"', scanner)

    def test_pos_javascript_uses_exact_barcode_endpoint(self):
        script_path = finders.find("js/pos.js")

        with open(script_path, encoding="utf-8") as script_file:
            script = script_file.read()
        self.assertIn('params.set("barcode", barcode)', script)
        self.assertIn('addProduct(products[0])', script)
        self.assertIn("Hay más de un producto con este código de barras", script)

    def test_workspace_uses_visual_catalog_mode_from_company_settings(self):
        CompanyOperationalSettings.objects.create(
            company=self.company,
            pos_product_search_mode=CompanyOperationalSettings.PosProductSearchMode.CATALOG,
        )
        self.activate_context()

        response = self.client.get("/pos/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-product-search-mode="CATALOG"')
        self.assertContains(response, 'id="pos-catalog-browser" class="pos-catalog-browser">')

    def test_workspace_denies_user_without_pos_permission(self):
        denied = User.objects.create_user(email="warehouse-web@pos.test", password="test")
        UserStore.objects.create(
            user=denied,
            store=self.store,
            role="WAREHOUSE",
            is_active=True,
        )
        self.client.force_login(denied)
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()

        response = self.client.get("/pos/")

        self.assertEqual(response.status_code, 403)

    def test_register_configuration_requires_its_own_permission(self):
        self.activate_context()

        response = self.client.get("/pos/configuracion/")

        self.assertEqual(response.status_code, 403)

    def test_authorized_user_can_create_register_from_web_configuration(self):
        action, module, description = next(
            item for item in POS_PERMISSION_DEFINITIONS
            if f"{item[0]}.{item[1]}" == "manage.pos.configuration"
        )
        permission, _ = Permission.objects.update_or_create(
            code="manage.pos.configuration",
            defaults={"action_name": action, "module": module, "description": description},
        )
        RolePermission.objects.create(role=self.role, permission=permission)
        warehouse = Warehouse.objects.create(store=self.store, name="Almacén principal")
        customer = Customer.objects.create(
            company=self.company,
            document_type="0",
            document_number="00000000",
            legal_name="VARIOS",
        )
        document_type = DocumentType.objects.create(
            code="NV", name="Nota de Venta", category="INTERNAL"
        )
        self.activate_context()

        response = self.client.post("/pos/configuracion/nueva/", {
            "code": "POS-01",
            "name": "Caja principal",
            "ticket_series": "T01",
            "default_warehouse": str(warehouse.pk),
            "default_price_list": "",
            "default_customer": str(customer.pk),
            "default_document_type": str(document_type.pk),
            "active": "on",
        })

        self.assertRedirects(response, "/pos/configuracion/")
        register = PosRegister.objects.get(code="POS-01")
        self.assertEqual(register.company, self.company)
        self.assertEqual(register.store, self.store)
        self.assertEqual(register.default_warehouse, warehouse)
