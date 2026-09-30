from django.test import TestCase

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
        self.assertIn("/login/", response.url)

    def test_workspace_renders_for_cashier_with_read_permission(self):
        self.activate_context()

        response = self.client.get("/pos/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "pos/sale.html")
        self.assertContains(response, "Nueva venta")
        self.assertContains(response, "/api/v1/pos/sales/checkout/")
        self.assertContains(response, 'id="checkout-review-dialog"')
        self.assertContains(response, "Esta es una precuenta")
        self.assertContains(response, "Confirmar y cobrar")
        self.assertContains(response, 'data-product-search-mode="SEARCH"')
        self.assertContains(response, 'id="pos-catalog-browser" class="pos-catalog-browser" hidden')

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
