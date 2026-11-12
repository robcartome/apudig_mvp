from decimal import Decimal

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.api.v1.auth.tokens import build_token
from apps.api.v1.users.helpers import make_token_pair
from apps.companies.models import Company, Store, UserCompanyAccess
from apps.inventory.models import Brand, Category, PriceList, Product, ProductPrice, ProductSupplier, StockByWarehouse, Unit, Warehouse
from apps.partners.models import Supplier
from apps.users.models import Permission, Role, RolePermission, User, UserRole
from apps.websites.models import Website, WebsiteDomain, WebsiteProduct


@override_settings(R2_PUBLIC_BASE_URL="https://media.apudig.com")
class CatalogTenantIsolationTest(TestCase):
    def setUp(self):
        self.company_a = Company.objects.create(name="Empresa A", ruc="20111111111")
        self.company_b = Company.objects.create(name="Empresa B", ruc="20222222222")
        self.unit = Unit.objects.create(code="NIU", name="Unidad")

        self.category_a = Category.objects.create(
            company=self.company_a,
            code="TOOLS",
            name="Herramientas",
        )
        self.category_a_other = Category.objects.create(
            company=self.company_a,
            code="ELEC",
            name="Electricidad",
        )
        self.category_b = Category.objects.create(
            company=self.company_b,
            code="TOOLS",
            name="Herramientas B",
        )
        self.brand_a = Brand.objects.create(company=self.company_a, name="Marca A")
        self.brand_a_other = Brand.objects.create(company=self.company_a, name="Marca A2")
        self.brand_b = Brand.objects.create(company=self.company_b, name="Marca B")

        self.product_a = Product.objects.create(
            company=self.company_a,
            name="Taladro A",
            sku="TAL-A",
            unit=self.unit,
            category=self.category_a,
            brand=self.brand_a,
            price_purchase=Decimal("120.00"),
            price_sale=Decimal("160.00"),
            active=True,
        )
        self.product_a_other = Product.objects.create(
            company=self.company_a,
            name="Cable A",
            sku="CAB-A",
            unit=self.unit,
            category=self.category_a_other,
            brand=self.brand_a_other,
            price_purchase=Decimal("8.00"),
            price_sale=Decimal("12.00"),
            active=True,
        )
        self.product_a_inactive = Product.objects.create(
            company=self.company_a,
            name="Producto inactivo A",
            sku="OFF-A",
            unit=self.unit,
            price_sale=Decimal("1.00"),
            active=False,
        )
        self.product_b = Product.objects.create(
            company=self.company_b,
            name="Taladro B",
            sku="TAL-B",
            unit=self.unit,
            category=self.category_b,
            brand=self.brand_b,
            price_purchase=Decimal("220.00"),
            price_sale=Decimal("260.00"),
            active=True,
        )

        supplier = Supplier.objects.create(
            company=self.company_a,
            name="Proveedor privado A",
            document_number="20111111112",
        )
        ProductSupplier.objects.create(
            product=self.product_a,
            supplier=supplier,
            supplier_code="PRIVATE-SUPPLIER-CODE",
            supplier_product_name="Nombre privado de proveedor",
            purchase_price=Decimal("110.00"),
        )

        self.website_a = Website.objects.create(
            company=self.company_a,
            name="Tienda A",
            status=Website.Status.PUBLISHED,
        )
        self.website_b = Website.objects.create(
            company=self.company_b,
            name="Tienda B",
            status=Website.Status.PUBLISHED,
        )
        WebsiteDomain.objects.create(
            website=self.website_a,
            hostname="a.apudig.test",
            status=WebsiteDomain.Status.ACTIVE,
            is_primary=True,
            verified_at=timezone.now(),
        )

        self.publication_a = WebsiteProduct.objects.create(
            website=self.website_a, product=self.product_a, is_published=True,
            commercial_title="Taladro profesional A",
        )
        WebsiteProduct.objects.create(
            website=self.website_a, product=self.product_a_other, is_published=True,
        )
        WebsiteProduct.objects.create(
            website=self.website_b, product=self.product_b, is_published=True,
        )
        self.price_list_a = PriceList.objects.create(
            company=self.company_a, name="Web A", active=True,
        )
        ProductPrice.objects.create(
            product=self.product_a, price_list=self.price_list_a,
            amount=Decimal("150.00"), currency="PEN",
        )
        self.store_a = Store.objects.create(company=self.company_a, name="Principal A")
        self.warehouse_a = Warehouse.objects.create(store=self.store_a, name="Web A")
        StockByWarehouse.objects.create(
            product=self.product_a, warehouse=self.warehouse_a, quantity=Decimal("7")
        )
        catalog_settings = self.website_a.catalog_settings
        catalog_settings.default_price_list = self.price_list_a
        catalog_settings.save()
        catalog_settings.warehouses.add(self.warehouse_a)
        WebsiteDomain.objects.create(
            website=self.website_b,
            hostname="b.apudig.test",
            status=WebsiteDomain.Status.ACTIVE,
            is_primary=True,
            verified_at=timezone.now(),
        )

        self.user_a = User.objects.create_user(email="user-a@test.com", password="pass")
        self.access_a = UserCompanyAccess.objects.create(
            user=self.user_a,
            company=self.company_a,
            store=None,
            is_default=True,
        )
        self.token_a = make_token_pair(self.user_a, self.access_a)["access"]
        self.generic_token = make_token_pair(self.user_a, None)["access"]
        self.forged_company_b_token = build_token(
            {
                "sub": str(self.user_a.pk),
                "email": self.user_a.email,
                "company_id": str(self.company_b.pk),
                "store_id": None,
                "roles": [],
                "permissions": [],
                "type": "access",
            },
            settings.JWT_ACCESS_TTL,
        )

    def auth(self, token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_legacy_catalog_requires_registered_site(self):
        response = self.client.get("/api/v1/catalog/products/")
        self.assertEqual(response.status_code, 400)

    def test_legacy_catalog_accepts_only_registered_site(self):
        response = self.client.get(
            "/api/v1/catalog/products/",
            {"site": "a.apudig.test", "limit": 20},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {item["id"] for item in response.json()["results"]},
            {str(self.product_a.pk), str(self.product_a_other.pk)},
        )

    def test_unknown_domain_returns_not_found(self):
        response = self.client.get(
            "/api/v1/storefront/sites/unknown.apudig.test/products/"
        )
        self.assertEqual(response.status_code, 404)

    def test_storefront_list_is_scoped_to_domain_company(self):
        response = self.client.get(
            "/api/v1/storefront/sites/a.apudig.test/products/",
            {"limit": 20},
        )
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.json()["results"]}
        self.assertEqual(ids, {str(self.product_a.pk), str(self.product_a_other.pk)})
        self.assertNotIn(str(self.product_b.pk), ids)
        self.assertNotIn(str(self.product_a_inactive.pk), ids)

    def test_only_explicitly_published_products_are_visible(self):
        unpublished = Product.objects.create(
            company=self.company_a, name="Oculto", sku="HIDDEN-A", unit=self.unit,
            price_sale=Decimal("10.00"), active=True,
        )
        response = self.client.get(
            "/api/v1/storefront/sites/a.apudig.test/products/", {"limit": 20}
        )
        self.assertNotIn(str(unpublished.pk), {item["id"] for item in response.json()["results"]})

    def test_public_price_and_availability_use_configured_sources(self):
        response = self.client.get(
            f"/api/v1/storefront/sites/a.apudig.test/products/{self.publication_a.slug}/"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["price"], "150.00")
        self.assertEqual(payload["availability"], "AVAILABLE")
        self.assertTrue(payload["available"])
        for private_field in ("public_stock", "stock_total", "stock_by_warehouse", "price_list"):
            self.assertNotIn(private_field, payload)

    def test_taxonomies_contain_only_published_products(self):
        categories = self.client.get(
            "/api/v1/storefront/sites/a.apudig.test/categories/"
        )
        brands = self.client.get("/api/v1/storefront/sites/a.apudig.test/brands/")
        self.assertEqual(categories.status_code, 200)
        self.assertEqual(brands.status_code, 200)
        self.assertEqual(
            {item["id"] for item in categories.json()},
            {str(self.category_a.pk), str(self.category_a_other.pk)},
        )
        self.assertNotIn(str(self.brand_b.pk), {item["id"] for item in brands.json()})

    def test_website_product_rejects_cross_tenant_product(self):
        publication = WebsiteProduct(website=self.website_a, product=self.product_b)
        with self.assertRaises(ValidationError):
            publication.full_clean()

    def test_catalog_pagination_has_stable_non_overlapping_pages_at_volume(self):
        products = [
            Product(
                company=self.company_a, name=f"Producto volumen {index:02d}",
                sku=f"VOL-{index:02d}", unit=self.unit, price_sale=Decimal("5.00"),
            )
            for index in range(30)
        ]
        Product.objects.bulk_create(products)
        WebsiteProduct.objects.bulk_create([
            WebsiteProduct(
                website=self.website_a, product=product,
                slug=f"producto-volumen-{index:02d}", is_published=True,
                position=100 + index,
            )
            for index, product in enumerate(products)
        ])
        first = self.client.get(
            "/api/v1/storefront/sites/a.apudig.test/products/",
            {"limit": 10, "offset": 0},
        ).json()
        second = self.client.get(
            "/api/v1/storefront/sites/a.apudig.test/products/",
            {"limit": 10, "offset": 10},
        ).json()
        self.assertEqual(first["total"], 32)
        self.assertEqual(len(first["results"]), 10)
        self.assertEqual(len(second["results"]), 10)
        self.assertFalse(
            {item["id"] for item in first["results"]}
            & {item["id"] for item in second["results"]}
        )

    def test_cart_quote_recalculates_price_and_signs_tenant_snapshot(self):
        response = self.client.post(
            "/api/v1/storefront/sites/a.apudig.test/cart/quote/",
            {"lines": [{
                "product_id": str(self.product_a.pk),
                "quantity": 2,
                "price": "0.01",
            }]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["total"], "300.00")
        self.assertEqual(payload["lines"][0]["price"], "150.00")
        self.assertEqual(payload["lines"][0]["subtotal"], "300.00")
        self.assertTrue(payload["can_submit"])
        signed = signing.loads(
            payload["quote_token"], salt="storefront-cart-quote-v1"
        )
        self.assertEqual(signed["website_id"], str(self.website_a.pk))
        self.assertEqual(signed["total"], "300.00")

    def test_cart_quote_marks_cross_tenant_and_retired_products_without_leaking_data(self):
        response = self.client.post(
            "/api/v1/storefront/sites/a.apudig.test/cart/quote/",
            {"lines": [{"product_id": str(self.product_b.pk), "quantity": 1}]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        line = response.json()["lines"][0]
        self.assertEqual(line["status"], "REMOVED")
        self.assertNotIn("name", line)
        self.assertNotIn("sku", line)
        self.assertFalse(response.json()["can_submit"])

        self.publication_a.is_published = False
        self.publication_a.save()
        retired = self.client.post(
            "/api/v1/storefront/sites/a.apudig.test/cart/quote/",
            {"lines": [{"product_id": str(self.product_a.pk), "quantity": 1}]},
            content_type="application/json",
        )
        self.assertEqual(retired.json()["lines"][0]["status"], "REMOVED")

    def test_cart_quote_flags_out_of_stock_and_rejects_invalid_quantities(self):
        unavailable = self.client.post(
            "/api/v1/storefront/sites/a.apudig.test/cart/quote/",
            {"lines": [{"product_id": str(self.product_a_other.pk), "quantity": 1}]},
            content_type="application/json",
        )
        self.assertEqual(unavailable.status_code, 200)
        self.assertEqual(unavailable.json()["lines"][0]["status"], "OUT_OF_STOCK")
        self.assertFalse(unavailable.json()["can_submit"])

        for quantity in (0, 1000):
            invalid = self.client.post(
                "/api/v1/storefront/sites/a.apudig.test/cart/quote/",
                {"lines": [{"product_id": str(self.product_a.pk), "quantity": quantity}]},
                content_type="application/json",
            )
            self.assertEqual(invalid.status_code, 400)

    @override_settings(STOREFRONT_QUOTE_RATE="2/min")
    def test_cart_quote_is_rate_limited_per_host_and_client(self):
        cache.clear()
        body = {"lines": [{"product_id": str(self.product_a.pk), "quantity": 1}]}
        first = self.client.post(
            "/api/v1/storefront/sites/a.apudig.test/cart/quote/", body,
            content_type="application/json",
        )
        second = self.client.post(
            "/api/v1/storefront/sites/a.apudig.test/cart/quote/", body,
            content_type="application/json",
        )
        limited = self.client.post(
            "/api/v1/storefront/sites/a.apudig.test/cart/quote/", body,
            content_type="application/json",
        )
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual(limited.status_code, 429)

    def test_storefront_detail_cannot_cross_company(self):
        response = self.client.get(
            f"/api/v1/storefront/sites/a.apudig.test/products/{self.product_b.pk}/"
        )
        self.assertEqual(response.status_code, 404)

    def test_storefront_search_and_filters_remain_scoped(self):
        search = self.client.get(
            "/api/v1/storefront/sites/a.apudig.test/products/",
            {"search": "Taladro", "limit": 20},
        )
        self.assertEqual(search.status_code, 200)
        self.assertEqual(
            [item["id"] for item in search.json()["results"]],
            [str(self.product_a.pk)],
        )

        filtered = self.client.get(
            "/api/v1/storefront/sites/a.apudig.test/products/",
            {
                "category": str(self.category_a_other.pk),
                "brand": str(self.brand_a_other.pk),
                "limit": 20,
            },
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(
            [item["id"] for item in filtered.json()["results"]],
            [str(self.product_a_other.pk)],
        )

        invalid = self.client.get(
            "/api/v1/storefront/sites/a.apudig.test/products/",
            {"category": "not-a-uuid"},
        )
        self.assertEqual(invalid.status_code, 400)

    def test_public_responses_omit_private_commercial_and_stock_fields(self):
        list_response = self.client.get(
            "/api/v1/storefront/sites/a.apudig.test/products/",
            {"search": "TAL-A"},
        )
        self.assertEqual(list_response.status_code, 200)
        item = list_response.json()["results"][0]
        for field in ("price_purchase", "supplier_codes", "stock", "stock_by_warehouse"):
            self.assertNotIn(field, item)

        detail_response = self.client.get(
            f"/api/v1/storefront/sites/a.apudig.test/products/{self.product_a.pk}/"
        )
        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()
        for field in (
            "price_purchase",
            "supplier_codes",
            "price_list",
            "stock_total",
            "stock_by_warehouse",
        ):
            self.assertNotIn(field, detail)

    def test_resolve_returns_public_identity_without_company_id(self):
        response = self.client.get(
            "/api/v1/storefront/resolve/",
            {"hostname": "A.APUDIG.TEST."},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["hostname"], "a.apudig.test")
        self.assertNotIn("company_id", response.json())

    def test_admin_product_endpoints_require_authentication(self):
        list_response = self.client.get("/api/v1/products/")
        detail_response = self.client.get(f"/api/v1/products/{self.product_a.pk}/")
        # The existing custom JWT authenticator has no WWW-Authenticate
        # challenge, so DRF rejects missing credentials with 403.
        self.assertEqual(list_response.status_code, 403)
        self.assertEqual(detail_response.status_code, 403)

    def test_admin_product_list_and_detail_are_scoped_to_authorized_company(self):
        list_response = self.client.get(
            "/api/v1/products/",
            {"limit": 20},
            **self.auth(self.token_a),
        )
        self.assertEqual(list_response.status_code, 200)
        ids = {item["id"] for item in list_response.json()["results"]}
        self.assertEqual(ids, {str(self.product_a.pk), str(self.product_a_other.pk)})

        cross_detail = self.client.get(
            f"/api/v1/products/{self.product_b.pk}/",
            **self.auth(self.token_a),
        )
        self.assertEqual(cross_detail.status_code, 404)

    def test_token_without_company_context_is_denied(self):
        response = self.client.get(
            "/api/v1/products/",
            **self.auth(self.generic_token),
        )
        self.assertEqual(response.status_code, 403)

    def test_signed_token_for_unauthorized_company_is_denied(self):
        response = self.client.get(
            "/api/v1/products/",
            **self.auth(self.forged_company_b_token),
        )
        self.assertEqual(response.status_code, 403)

    def test_configured_inventory_permission_is_enforced(self):
        permission = Permission.objects.create(
            code="read.inventory.products",
            action_name=Permission.ACTION_READ,
            module="inventory.products",
            description="Leer productos",
        )
        denied = self.client.get(
            "/api/v1/products/",
            **self.auth(self.token_a),
        )
        self.assertEqual(denied.status_code, 403)

        role = Role.objects.create(name="INVENTORY_READER")
        RolePermission.objects.create(role=role, permission=permission)
        UserRole.objects.create(user=self.user_a, role=role, company=self.company_a)
        allowed = self.client.get(
            "/api/v1/products/",
            **self.auth(self.token_a),
        )
        self.assertEqual(allowed.status_code, 200)

    def test_private_catalog_is_scoped_and_keeps_internal_fields(self):
        response = self.client.get(
            "/api/v1/catalog/private/products/",
            {"limit": 20},
            **self.auth(self.token_a),
        )
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(
            {item["id"] for item in results},
            {str(self.product_a.pk), str(self.product_a_other.pk)},
        )
        taladro = next(item for item in results if item["id"] == str(self.product_a.pk))
        self.assertEqual(taladro["price_purchase"], "120.00")
