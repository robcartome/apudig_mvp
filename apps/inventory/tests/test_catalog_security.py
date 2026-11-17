import datetime

from django.conf import settings
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.api.v1.auth.tokens import build_token
from apps.companies.models import Company, Store, UserCompanyAccess
from apps.inventory.models import Brand, Category, Product, Unit, PriceList, ProductPrice, StockByWarehouse, Warehouse, ProductSupplier
from apps.partners.models import Supplier
from apps.users.models import User, Role, UserRole, RolePermission, Permission, UserStore


class CatalogSecurityTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Company.objects.create(name="Catalog A", ruc="20999000201")
        cls.b = Company.objects.create(name="Catalog B", ruc="20999000202")
        cls.unit = Unit.objects.create(code="CATSEC", name="Unit")
        cls.product = Product.objects.create(company=cls.a, name="Worker A", sku="WORK-A", unit=cls.unit, price_sale="12.00", price_purchase="5.00")
        cls.foreign = Product.objects.create(company=cls.b, name="Worker B", sku="WORK-B", unit=cls.unit, price_sale="20.00", price_purchase="7.00")
        cls.store = Store.objects.create(company=cls.a, name="Store A")
        cls.foreign_store = Store.objects.create(company=cls.b, name="Store B")
        cls.warehouse = Warehouse.objects.create(store=cls.store, name="Warehouse A")
        cls.foreign_warehouse = Warehouse.objects.create(store=cls.foreign_store, name="Warehouse B")
        StockByWarehouse.objects.create(product=cls.product, warehouse=cls.warehouse, quantity="6.000")
        StockByWarehouse.objects.create(product=cls.product, warehouse=cls.foreign_warehouse, quantity="99.000")
        cls.price_list = PriceList.objects.create(company=cls.a, name="Internal A")
        cls.foreign_list = PriceList.objects.create(company=cls.b, name="Internal B")
        ProductPrice.objects.create(product=cls.product, price_list=cls.price_list, amount="11.00")
        ProductPrice.objects.create(product=cls.product, price_list=cls.foreign_list, amount="99.00")
        supplier = Supplier.objects.create(company=cls.a, name="Supplier A", document_number="20999000203")
        ProductSupplier.objects.create(product=cls.product, supplier=supplier, supplier_code="PRIVATE-A")
        cls.reader = User.objects.create_user(email="catalog-reader@example.test")
        cls.administrator = User.objects.create_user(email="catalog-admin@example.test")
        cls.root = User.objects.create_user(email="catalog-root@example.test", is_superuser=True)
        for user in (cls.reader, cls.administrator):
            UserCompanyAccess.objects.create(user=user, company=cls.a)
        cls.reader_role = Role.objects.create(name="Catalog reader test")
        read, _ = Permission.objects.get_or_create(code="read.inventory.products", defaults={"action_name": "read", "module": "inventory.products"})
        RolePermission.objects.create(role=cls.reader_role, permission=read)
        UserRole.objects.create(user=cls.reader, company=cls.a, role=cls.reader_role)
        role, _ = Role.objects.get_or_create(name="ADMIN")
        UserRole.objects.create(user=cls.administrator, company=cls.a, role=role)

    def token(self, user=None, company=True, **claims):
        payload = {"sub": str((user or self.reader).pk), "type": "access"}
        if company:
            payload["company_id"] = str(self.a.pk)
        return build_token({**payload, **claims}, settings.JWT_ACCESS_TTL)

    def get(self, path, token=None, **query):
        return self.client.get(path, query, HTTP_AUTHORIZATION=f"Bearer {token or self.token()}")

    def test_anonymous_denied_before_product_queries_for_all_six_read_routes(self):
        paths = ("catalog/products/", f"catalog/products/{self.product.pk}/detail/", "catalog/private/products/", f"catalog/private/products/{self.product.pk}/detail/", "products/", f"products/{self.product.pk}/")
        for path in paths:
            with self.subTest(path=path), CaptureQueriesContext(connection) as queries:
                response = self.client.get("/api/v1/" + path)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response["WWW-Authenticate"], "Bearer")
                self.assertFalse(any('FROM "products"' in q["sql"] for q in queries))

    def test_company_required_for_generic_and_superuser_tokens(self):
        for user in (self.reader, self.root):
            response = self.get("/api/v1/catalog/products/", self.token(user, company=False), company_id=str(self.b.pk))
            self.assertEqual(response.status_code, 403)

    def test_profile_exposes_actual_superuser_status_for_navigation(self):
        for user in (self.reader, self.root):
            with self.subTest(user=user.email):
                response = self.get("/api/v1/auth/me/", self.token(user, is_superuser=not user.is_superuser))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["is_superuser"], user.is_superuser)

    def test_current_membership_company_and_permission_are_revalidated(self):
        token = self.token()
        UserCompanyAccess.objects.filter(user=self.reader).delete()
        self.assertEqual(self.get("/api/v1/catalog/products/", token).status_code, 403)
        self.assertEqual(self.get("/api/v1/catalog/private/products/", self.token(self.administrator)).status_code, 200)
        self.a.is_active = False
        self.a.save()
        self.assertEqual(self.get("/api/v1/catalog/products/", token).status_code, 403)
        self.assertEqual(self.get("/api/v1/catalog/private/products/", self.token(self.root)).status_code, 403)

    def test_missing_inventory_grant_does_not_block_basic_catalog(self):
        RolePermission.objects.filter(role=self.reader_role).delete()
        self.assertEqual(self.get("/api/v1/catalog/products/").status_code, 200)
        self.assertEqual(self.get("/api/v1/products/").status_code, 403)
        UserCompanyAccess.objects.filter(user=self.administrator).delete()
        self.assertEqual(self.get("/api/v1/catalog/private/products/", self.token(self.administrator)).status_code, 403)

    def test_members_without_roles_and_sellers_and_cashiers_can_read_only_basic_catalog(self):
        UserRole.objects.filter(user=self.reader).delete()
        for role_name in (None, "SELLER", "CASHIER"):
            with self.subTest(role=role_name):
                UserRole.objects.filter(user=self.reader).delete()
                if role_name:
                    role, _ = Role.objects.get_or_create(name=role_name)
                    UserRole.objects.create(user=self.reader, company=self.a, role=role)
                token = self.token()
                response = self.get("/api/v1/catalog/products/", token)
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row["id"] for row in response.json()["results"]], [str(self.product.pk)])
                detail = self.get(f"/api/v1/catalog/products/{self.product.pk}/detail/", token)
                self.assertEqual(detail.status_code, 200)
                for field in ("price_purchase", "supplier_codes", "price_list", "stock_by_warehouse"):
                    self.assertNotIn(field, detail.json())
                self.assertEqual(self.get("/api/v1/catalog/private/products/", token).status_code, 403)
                self.assertEqual(self.get(f"/api/v1/catalog/products/{self.foreign.pk}/detail/", token).status_code, 404)
        UserCompanyAccess.objects.filter(user=self.reader).delete()
        self.assertEqual(self.get("/api/v1/catalog/products/", token).status_code, 403)

    def test_basic_envelope_filters_and_detail_exclude_private_fields(self):
        response = self.get("/api/v1/catalog/products/", search="Worker", limit=1, offset=0, company_id=str(self.b.pk))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        page = response.json()
        self.assertEqual(set(page), {"total", "results", "limit", "offset"})
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["results"][0]["id"], str(self.product.pk))
        self.assertEqual(page["results"][0]["stock"], 6.0)
        for path in (f"catalog/products/{self.product.pk}/detail/", f"products/{self.product.pk}/"):
            detail = self.get("/api/v1/" + path).json()
            for field in ("price_purchase", "price_list", "stock_by_warehouse", "supplier_codes"):
                self.assertNotIn(field, detail)
        self.assertEqual(self.get("/api/v1/catalog/products/", search="PRIVATE-A").json()["total"], 0)

    def test_private_endpoint_requires_company_administration(self):
        self.assertEqual(self.get("/api/v1/catalog/private/products/").status_code, 403)
        for user in (self.administrator, self.root):
            response = self.get(f"/api/v1/catalog/private/products/{self.product.pk}/detail/", self.token(user))
            self.assertEqual(response.status_code, 200, response.content)
            data = response.json()
            self.assertEqual(data["price_purchase"], "5.00")
            self.assertEqual([p["price_list_name"] for p in data["price_list"]], ["Internal A"])
            self.assertEqual([w["warehouse_name"] for w in data["stock_by_warehouse"]], ["Warehouse A"])
            self.assertEqual(data["supplier_codes"], ["PRIVATE-A"])

    def test_foreign_detail_and_store_claim_are_rejected(self):
        for path in (f"catalog/products/{self.foreign.pk}/detail/", f"products/{self.foreign.pk}/"):
            self.assertEqual(self.get("/api/v1/" + path).status_code, 404)
        self.assertEqual(self.get("/api/v1/catalog/products/", self.token(store_id=str(self.foreign_store.pk))).status_code, 403)

    def test_store_admin_cannot_read_private_catalog_and_inactive_store_is_denied(self):
        UserStore.objects.create(user=self.reader, store=self.store, role="ADMIN")
        token = self.token(store_id=str(self.store.pk))
        self.assertEqual(self.get("/api/v1/catalog/products/", token).status_code, 200)
        self.assertEqual(self.get("/api/v1/catalog/private/products/", token).status_code, 403)
        self.store.active = False
        self.store.save()
        self.assertEqual(self.get("/api/v1/catalog/products/", token).status_code, 403)

    def test_malformed_and_expired_credentials_do_not_expose_data(self):
        self.assertEqual(self.get("/api/v1/catalog/products/", self.token(company_id="invalid")).status_code, 403)
        self.assertEqual(self.get("/api/v1/catalog/products/", "invalid.token").status_code, 401)
        expired = build_token({"sub": str(self.reader.pk), "type": "access", "company_id": str(self.a.pk)}, datetime.timedelta(seconds=-5))
        self.assertEqual(self.get("/api/v1/catalog/products/", expired).status_code, 401)

    def test_invalid_filters_return_validation_error_without_global_fallback(self):
        for path in ("catalog/products/", "products/"):
            for field in ("brand", "category"):
                with self.subTest(path=path, field=field):
                    response = self.get("/api/v1/" + path, **{field: "invalid"})
                    self.assertEqual(response.status_code, 400)
                    self.assertIn(field, response.json())

    def test_foreign_relations_are_redacted_and_not_searchable(self):
        self.product.brand = Brand.objects.create(company=self.b, name="Foreign brand")
        self.product.category = Category.objects.create(company=self.b, name="Foreign category", code="FOREIGN")
        self.product.save()
        supplier = Supplier.objects.create(company=self.b, name="Foreign supplier", document_number="20999000204")
        # Simulate a corrupt legacy relation without bypassing validation in production code.
        ProductSupplier.objects.bulk_create([ProductSupplier(company=self.a, product=self.product, supplier=supplier, supplier_code="SECRET-B")])
        token = self.token(self.administrator)
        response = self.get(f"/api/v1/catalog/private/products/{self.product.pk}/detail/", token)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["brand"])
        self.assertIsNone(response.json()["category"])
        self.assertEqual(response.json()["supplier_codes"], ["PRIVATE-A"])
        self.assertEqual(self.get("/api/v1/catalog/private/products/", token, search="SECRET-B").json()["total"], 0)
        self.assertEqual(self.get("/api/v1/catalog/products/", brand=str(self.product.brand_id)).json()["total"], 0)

    def test_inactive_warehouse_is_excluded_from_totals_and_private_detail(self):
        self.warehouse.active = False
        self.warehouse.save()
        response = self.get(f"/api/v1/catalog/private/products/{self.product.pk}/detail/", self.token(self.administrator))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stock_total"], 0)
        self.assertEqual(response.json()["stock_by_warehouse"], [])

    def test_old_admin_claim_does_not_replace_current_company_role(self):
        token = self.token(self.administrator, roles=["ADMIN"], is_superuser=True)
        UserRole.objects.filter(user=self.administrator, company=self.a).delete()
        UserRole.objects.create(user=self.administrator, company=self.a, role=self.reader_role)
        self.assertEqual(self.get("/api/v1/catalog/products/", token).status_code, 200)
        self.assertEqual(self.get("/api/v1/catalog/private/products/", token).status_code, 403)
        RolePermission.objects.filter(role=self.reader_role).delete()
        self.assertEqual(self.get("/api/v1/catalog/products/", token).status_code, 200)
        self.assertEqual(self.get("/api/v1/products/", token).status_code, 403)
