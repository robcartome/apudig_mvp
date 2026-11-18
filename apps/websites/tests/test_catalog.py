import json
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from time import perf_counter
from unittest import skipUnless

from django.conf import settings
from django.db import close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.api.v1.auth.tokens import build_token
from apps.companies.models import Company, Store, TaxRate, UserCompanyAccess
from apps.core.models import AuditLog
from apps.inventory.models import Brand, Category, PriceList, Product, ProductPrice, ProductUnit, StockByWarehouse, Unit, Warehouse
from apps.users.models import Permission, Role, RolePermission, User, UserRole
from apps.websites.catalog import selectors, services
from apps.websites.errors import WebsiteError
from apps.websites.models import Website, WebsiteCatalogSettings, WebsiteDomain, WebsitePage, WebsitePageRevision, WebsiteProduct
from .test_editorial import editorial_fixture


class CommercialCatalogFixture:
    def setUp(self):
        super().setUp()
        self.a = Company.objects.create(name="Catalog Company A", ruc="20999110001")
        self.b = Company.objects.create(name="Catalog Company B", ruc="20999110002")
        self.site = self.published_site(self.a, "a.catalog.test")
        self.foreign_site = self.published_site(self.b, "b.catalog.test")
        self.unit = Unit.objects.create(code="CATBASE", name="Unidad base")
        self.pack = Unit.objects.create(code="CATPACK", name="Paquete")
        self.category = Category.objects.create(company=self.a, code="TOOLS", name="Herramientas")
        self.other_category = Category.objects.create(company=self.a, code="PAINT", name="Pinturas")
        self.brand = Brand.objects.create(company=self.a, name="Marca A")
        self.other_brand = Brand.objects.create(company=self.a, name="Marca Alterna")
        self.product = Product.objects.create(company=self.a, unit=self.unit, category=self.category, brand=self.brand, sku="PUBLIC-A", name="Producto A", price_sale="999", price_purchase="555")
        self.second = Product.objects.create(company=self.a, unit=self.unit, category=self.other_category, brand=self.other_brand, sku="SECOND-A", name="Segundo A")
        self.foreign = Product.objects.create(company=self.b, unit=self.unit, sku="FOREIGN-B", name="Producto privado B")
        self.unpublished = Product.objects.create(company=self.a, unit=self.unit, sku="DRAFT-A", name="Producto no publicado")
        self.conversion = ProductUnit.objects.create(product=self.product, unit=self.pack, conversion_factor=6, is_default_sale=True, sale_price="0.01", purchase_price="0.01")
        self.price_list = PriceList.objects.create(company=self.a, name="Public authorized A", prices_include_tax=False)
        self.foreign_list = PriceList.objects.create(company=self.b, name="Private B")
        self.price = ProductPrice.objects.create(product=self.product, price_list=self.price_list, amount="10", currency="PEN")
        ProductPrice.objects.create(product=self.second, price_list=self.price_list, amount="20", currency="PEN")
        self.store = Store.objects.create(company=self.a, name="Store A")
        self.foreign_store = Store.objects.create(company=self.b, name="Store B")
        self.warehouse = Warehouse.objects.create(store=self.store, name="Authorized warehouse A")
        self.foreign_warehouse = Warehouse.objects.create(store=self.foreign_store, name="Private warehouse B")
        self.stock = StockByWarehouse.objects.create(product=self.product, warehouse=self.warehouse, quantity=8)
        StockByWarehouse.objects.create(product=self.product, warehouse=self.foreign_warehouse, quantity=999)
        self.configuration = WebsiteCatalogSettings.objects.create(website=self.site, default_price_list=self.price_list)
        self.configuration.warehouses.add(self.warehouse)
        self.publication = WebsiteProduct.objects.create(website=self.site, product=self.product, is_published=True, commercial_title="Oferta A", is_featured=True)
        self.second_publication = WebsiteProduct.objects.create(website=self.site, product=self.second, is_published=True)
        WebsiteProduct.objects.create(website=self.site, product=self.unpublished)
        WebsiteProduct.objects.create(website=self.foreign_site, product=self.foreign, is_published=True)
        self.admin = self.member("admin", ["ADMIN"])
        self.editor = self.member("editor", ["Catalog editor"])
        self.reader = self.member("reader", ["Catalog read"])
        self.media = self.member("media", ["Catalog media"])
        self.worker = self.member("worker", [])
        for role_name, codes in (
            ("Catalog editor", ["read.website", "manage.website", "publish.website"]),
            ("Catalog read", ["read.website"]),
            ("Catalog media", ["manage.website.media", "manage.website.domains"]),
        ):
            role = Role.objects.get(name=role_name)
            for code in codes:
                action, module = code.split(".", 1)
                permission, _ = Permission.objects.get_or_create(code=code, defaults={"action_name": action, "module": module})
                RolePermission.objects.get_or_create(role=role, permission=permission)
        self.public = Client()
        self.client = self.authenticated(self.admin)

    def published_site(self, company, hostname):
        website = Website.objects.create(company=company, name=company.name)
        page = WebsitePage.objects.create(website=website, slug="home", title="Home", page_type="HOME", status="PUBLISHED", draft_version=1, published_version=1)
        revision = WebsitePageRevision.objects.create(page=page, version=1, operation="PUBLISH", editorial_revision=1, snapshot={"schemaVersion": 3, "templateKey": "ecommerce", "document": editorial_fixture()})
        website.status = "PUBLISHED"
        website.published_revision = revision
        website.editorial_revision = 1
        website.published_at = timezone.now()
        website.save()
        WebsiteDomain.objects.create(website=website, hostname=hostname, status="ACTIVE", verified_at=timezone.now())
        return website

    def member(self, name, roles):
        user = User.objects.create_user(email=name + "@catalog.example.test")
        UserCompanyAccess.objects.create(user=user, company=self.a)
        for name in roles:
            role, _ = Role.objects.get_or_create(name=name)
            UserRole.objects.create(user=user, company=self.a, role=role)
        return user

    def authenticated(self, user, **claims):
        token = build_token({"sub": str(user.pk), "type": "access", "company_id": str(self.a.pk), **claims}, settings.JWT_ACCESS_TTL)
        return Client(HTTP_AUTHORIZATION="Bearer " + token)

    def public_url(self, suffix="products/", host="a.catalog.test"):
        return f"/api/v1/storefront/sites/{host}/{suffix}"

    def admin_url(self, suffix="catalog-settings/", website=None):
        return f"/api/v1/websites/{(website or self.site).pk}/{suffix}"

    def etag(self, client=None):
        return (client or self.client).get(self.admin_url())["ETag"]

    def patch_settings(self, data, client=None, etag=None):
        client = client or self.client
        return client.patch(self.admin_url(), data, content_type="application/json", HTTP_IF_MATCH=etag or self.etag(client))


class WebsiteCatalogTest(CommercialCatalogFixture, TestCase):
    def test_published_home_keeps_editorial_sections_but_live_eligibility_controls_references(self):
        revision = self.site.published_revision
        snapshot = revision.snapshot
        document = snapshot["document"]
        for section in document["sections"]:
            if section["type"] in ("featured", "specials"):
                section["enabled"] = True
        document["specials"]["productIds"] = [str(self.product.pk), str(self.foreign.pk), str(self.unpublished.pk), "old-demo-id"]
        revision.page.published_version = 2
        revision.page.draft_version = 2
        revision.page.save(update_fields=["published_version", "draft_version"])
        revision = WebsitePageRevision.objects.create(page=revision.page, version=2, operation="PUBLISH", editorial_revision=2, snapshot=snapshot)
        self.site.published_revision = revision
        self.site.editorial_revision = 2
        self.site.save(update_fields=["published_revision", "editorial_revision"])
        path = "/api/v1/storefront/sites/a.catalog.test/content/"
        initial = self.public.get(path).json()
        self.assertIn("featured", {row["type"] for row in initial["content"]["sections"]})
        self.assertEqual(initial["content"]["specials"]["productIds"], [str(self.product.pk)])
        self.assertFalse(initial["commerceEnabled"])
        self.publication.is_published = False
        self.publication.save(update_fields=["is_published"])
        retired = self.public.get(path).json()
        self.assertEqual(retired["content"]["specials"]["productIds"], [])
        self.assertEqual(retired["revision"], initial["revision"])
        revision.refresh_from_db()
        self.assertEqual(revision.snapshot, snapshot)

    def test_public_dto_uses_authorized_taxed_pack_price_and_hides_private_fields(self):
        response = self.public.get(self.public_url(), {"ordering": "price-desc"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("no-store", response["Cache-Control"])
        page = response.json()
        self.assertEqual(page["count"], 2)
        product = page["results"][0]
        self.assertEqual(product["id"], str(self.product.pk))
        self.assertEqual(product["price"], "70.80")
        self.assertEqual(product["unitId"], str(self.pack.pk))
        self.assertEqual(product["availability"], "available")
        self.assertIsNone(product["original_price"])
        for key in ("price_purchase", "price_sale", "purchase_price", "supplier_codes", "stock_by_warehouse", "warehouses", "companyId", "priceListId", "offer_stock", "inventory_unit_cost"):
            self.assertNotIn(key, json.dumps(page))
        detail = self.public.get(self.public_url(f"products/{self.product.pk}/")).json()["product"]
        self.assertEqual(detail["price"], product["price"])
        prices = {row["unitId"]: row["price"] for row in detail["saleUnits"]}
        self.assertEqual(prices, {str(self.unit.pk): "11.80", str(self.pack.pk): "70.80"})

    def test_inclusive_and_exempt_taxes_and_unit_fallback(self):
        today = timezone.localdate()
        TaxRate.objects.create(company=self.a, code="VALID", rate=5, valid_from=today - timedelta(days=1), valid_until=today + timedelta(days=1), is_default=True)
        TaxRate.objects.create(company=self.a, code="EXPIRED", rate=99, valid_from=today - timedelta(days=5), valid_until=today - timedelta(days=1))
        TaxRate.objects.create(company=self.a, code="FUTURE", rate=99, valid_from=today + timedelta(days=1))
        self.assertEqual(self.public.get(self.public_url(f"products/{self.product.pk}/")).json()["product"]["price"], "63.00")
        self.price_list.prices_include_tax = True
        self.price_list.save()
        self.assertEqual(self.public.get(self.public_url(f"products/{self.product.pk}/")).json()["product"]["price"], "60.00")
        self.price_list.prices_include_tax = False
        self.price_list.save()
        self.product.tax_affectation = "20"
        self.product.save()
        self.assertEqual(self.public.get(self.public_url(f"products/{self.product.pk}/")).json()["product"]["price"], "60.00")
        self.conversion.active = False
        self.conversion.save()
        product = self.public.get(self.public_url(f"products/{self.product.pk}/")).json()["product"]
        self.assertEqual(product["unitId"], str(self.unit.pk))
        self.assertEqual(product["price"], "10.00")

    def test_missing_inactive_foreign_negative_or_wrong_currency_price_never_falls_back(self):
        override = PriceList.objects.create(company=self.a, name="Authorized override")
        self.publication.price_list = override
        self.publication.save()
        for mutation in ("missing", "inactive", "foreign", "currency", "negative"):
            ProductPrice.objects.filter(product=self.product, price_list=override).delete()
            WebsiteProduct.objects.filter(pk=self.publication.pk).update(price_list=override)
            override.active = True
            override.save()
            if mutation == "inactive":
                override.active = False
                override.save()
            elif mutation == "foreign":
                WebsiteProduct.objects.filter(pk=self.publication.pk).update(price_list=self.foreign_list)
            elif mutation == "currency":
                ProductPrice.objects.create(product=self.product, price_list=override, amount=1, currency="USD")
            elif mutation == "negative":
                ProductPrice.objects.create(product=self.product, price_list=override, amount=-1)
            with self.subTest(mutation=mutation):
                self.assertIsNone(self.public.get(self.public_url(f"products/{self.product.pk}/")).json()["product"]["price"])
        WebsiteProduct.objects.filter(pk=self.publication.pk).update(price_list=None)
        self.configuration.default_price_list = None
        self.configuration.save()
        self.assertIsNone(self.public.get(self.public_url(f"products/{self.product.pk}/")).json()["product"]["price"])

    def test_zero_price_and_rounding_are_not_missing_price(self):
        self.price.amount = 0
        self.price.save()
        self.assertEqual(self.public.get(self.public_url(f"products/{self.product.pk}/")).json()["product"]["price"], "0.00")
        self.price.amount = Decimal("0.01")
        self.price.save()
        self.conversion.conversion_factor = Decimal("1.234567")
        self.conversion.save()
        result = self.public.get(self.public_url(f"products/{self.product.pk}/")).json()["product"]
        self.assertEqual(result["price"], "0.01")
        self.assertEqual(next(row for row in result["saleUnits"] if row["unitId"] == result["unitId"])["price"], result["price"])

    def test_stock_uses_only_explicit_active_company_warehouses_and_unit_factor(self):
        self.stock.quantity = 5
        self.stock.save()
        result = self.public.get(self.public_url(f"products/{self.product.pk}/")).json()["product"]
        self.assertEqual(result["availability"], "unavailable")
        self.assertEqual(result["saleUnits"][0]["availability"], "available")
        self.configuration.warehouses.add(self.foreign_warehouse)
        self.assertEqual(self.public.get(self.public_url(f"products/{self.product.pk}/")).json()["product"]["availability"], "unavailable")
        self.configuration.warehouses.clear()
        self.assertEqual(self.public.get(self.public_url(f"products/{self.product.pk}/")).json()["product"]["availability"], "unknown")
        self.configuration.warehouses.add(self.warehouse)
        self.warehouse.active = False
        self.warehouse.save()
        self.assertEqual(self.public.get(self.public_url(f"products/{self.product.pk}/")).json()["product"]["availability"], "unknown")

    def test_negative_stock_services_and_hide_unavailable(self):
        self.stock.quantity = -3
        self.stock.save()
        self.configuration.show_out_of_stock = False
        self.configuration.save()
        self.assertEqual(self.public.get(self.public_url()).json()["count"], 0)
        self.product.tracks_inventory = False
        self.product.save()
        result = self.public.get(self.public_url()).json()
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0]["availability"], "unknown")

    def test_unknown_inactive_unverified_unpublished_sites_and_foreign_resources_fail_closed(self):
        for host in ("unknown.catalog.test", "127.0.0.1", "a.catalog.test:8000"):
            for suffix in ("products/", "categories/", "brands/"):
                self.assertEqual(self.public.get(self.public_url(suffix, host)).status_code, 404)
        self.assertEqual(self.public.get(self.public_url(f"products/{self.foreign.pk}/")).status_code, 404)
        self.assertEqual(self.public.get(self.public_url(f"products/{self.unpublished.pk}/")).status_code, 404)
        Product.objects.filter(pk=self.product.pk).update(active=False)
        self.assertEqual(self.public.get(self.public_url(f"products/{self.product.pk}/")).status_code, 404)
        Product.objects.filter(pk=self.product.pk).update(active=True)
        result = self.public.get(self.public_url(host="b.catalog.test")).json()
        self.assertEqual([row["id"] for row in result["results"]], [str(self.foreign.pk)])
        for state in ("DISABLED", "PENDING"):
            WebsiteDomain.objects.filter(website=self.site).update(status=state, verified_at=None, is_primary=False)
            self.assertEqual(self.public.get(self.public_url()).status_code, 404)
        WebsiteDomain.objects.filter(website=self.site).update(status="ACTIVE", verified_at=timezone.now())
        Website.objects.filter(pk=self.site.pk).update(status="DRAFT")
        self.assertEqual(self.public.get(self.public_url()).status_code, 404)
        Website.objects.filter(pk=self.site.pk).update(status="PUBLISHED")
        Company.objects.filter(pk=self.a.pk).update(is_active=False)
        self.assertEqual(self.public.get(self.public_url()).status_code, 404)

    def test_filters_pagination_facets_and_public_search_use_displayed_offer(self):
        page = self.public.get(self.public_url(), {"limit": 1, "offset": 1, "ordering": "price-asc"}).json()
        self.assertEqual(page["count"], 2)
        self.assertEqual(page["results"][0]["id"], str(self.product.pk))
        page = self.public.get(self.public_url(), {"category": str(self.category.pk), "min": "60", "max": "80"}).json()
        self.assertEqual(page["count"], 1)
        self.assertEqual(page["facets"]["categories"][0]["productCount"], 1)
        page = self.public.get(self.public_url(), {"category": [str(self.category.pk), str(self.other_category.pk)]}).json()
        self.assertEqual(page["count"], 2)
        page = self.public.get(self.public_url(), {"category": str(self.category.pk)}).json()
        self.assertEqual(len(page["facets"]["categories"]), 2)
        self.assertEqual(len(page["facets"]["brands"]), 1)
        self.assertEqual(self.public.get(self.public_url(), {"search": "Oferta A"}).json()["count"], 1)
        self.assertEqual(self.public.get(self.public_url(), {"featured": "true"}).json()["count"], 1)
        for params in ({"ordering": "discount"}, {"min": "NaN"}, {"min": "20", "max": "10"}, {"limit": "101"}, {"offset": "-1"}, {"category": "bad"}, {"company_id": str(self.b.pk)}, {"price_list_id": str(self.foreign_list.pk)}):
            self.assertEqual(self.public.get(self.public_url(), params).status_code, 400, params)

    def test_categories_and_brands_only_count_eligible_products(self):
        for suffix in ("categories/", "brands/"):
            page = self.public.get(self.public_url(suffix), {"limit": 1}).json()
            self.assertEqual(page["count"], 2)
            self.assertEqual(len(page["results"]), 1)
            self.assertEqual(page["results"][0]["productCount"], 1)
        WebsiteProduct.objects.filter(pk=self.second_publication.pk).update(is_published=False)
        self.assertEqual(self.public.get(self.public_url("categories/")).json()["count"], 1)
        Category.objects.filter(pk=self.category.pk).update(company=self.b)
        self.assertEqual(self.public.get(self.public_url("categories/")).json()["count"], 0)
        product = self.public.get(self.public_url(f"products/{self.product.pk}/")).json()["product"]
        self.assertIsNone(product["category"])

    def test_price_stock_and_units_update_without_editorial_publication_or_commercial_etag_change(self):
        etag = self.etag()
        self.price.amount = 15
        self.price.save()
        self.stock.quantity = 1
        self.stock.save()
        result = self.public.get(self.public_url(f"products/{self.product.pk}/")).json()["product"]
        self.assertEqual(result["price"], "106.20")
        self.assertEqual(result["availability"], "unavailable")
        self.assertEqual(self.etag(), etag)
        self.site.refresh_from_db()
        self.assertEqual(self.site.editorial_revision, 1)
        self.assertEqual(WebsitePageRevision.objects.filter(page__website=self.site).count(), 1)
        self.assertFalse(self.public.get(self.public_url("content/")).json()["commerceEnabled"])

    def test_configuration_get_has_no_side_effects_and_commercial_etag_is_separate(self):
        self.configuration.delete()
        response = self.client.get(self.admin_url())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(WebsiteCatalogSettings.objects.filter(website=self.site).exists())
        self.assertFalse(response.json()["commerceEnabled"])
        self.assertTrue(response["ETag"].startswith('"catalog-'))
        self.assertEqual(self.client.patch(self.admin_url(), {}, content_type="application/json").status_code, 428)
        self.assertEqual(self.patch_settings({}, etag='"1"').status_code, 400)
        previous = response["ETag"]
        saved = self.patch_settings({"defaultPriceListId": str(self.price_list.pk), "warehouseIds": [str(self.warehouse.pk)]}, etag=previous)
        self.assertEqual(saved.status_code, 200, saved.content)
        self.assertNotEqual(saved["ETag"], previous)
        self.assertEqual(self.patch_settings({"productsPerPage": 5}, etag=previous).status_code, 412)

    def test_configured_page_size_is_default_and_explicit_api_limit_remains_bounded(self):
        self.assertEqual(self.patch_settings({"productsPerPage": 1}).status_code, 200)
        page = self.public.get(self.public_url()).json()
        self.assertEqual(page["count"], 2)
        self.assertEqual(page["limit"], 1)
        self.assertEqual(len(page["results"]), 1)
        self.assertEqual(len(self.public.get(self.public_url(), {"limit": 2}).json()["results"]), 2)

    def test_price_policy_requires_company_admin_and_never_exposes_internal_options_to_cms(self):
        editor = self.authenticated(self.editor)
        configuration = editor.get(self.admin_url())
        self.assertEqual(configuration.status_code, 200)
        for field in ("priceListOptions", "warehouseOptions", "defaultPriceListId", "warehouseIds"):
            self.assertNotIn(field, configuration.json())
        self.assertEqual(self.patch_settings({"productsPerPage": 8}, client=editor).status_code, 403)
        response = editor.patch(self.admin_url(f"products/{self.publication.pk}/"), {"priceListId": None}, content_type="application/json", HTTP_IF_MATCH=configuration["ETag"])
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.authenticated(self.media).get(self.admin_url()).status_code, 403)
        self.assertEqual(self.authenticated(self.reader).get(self.admin_url("catalog-product-options/")).status_code, 403)
        self.assertEqual(editor.get(self.admin_url("catalog-product-options/")).status_code, 200)
        self.assertEqual(self.authenticated(self.worker).get(self.admin_url()).status_code, 403)

    def test_admin_authentication_and_scoping_reject_missing_stale_and_malformed_context(self):
        for suffix in ("catalog-settings/", "catalog-product-options/", "products/"):
            path = self.admin_url(suffix)
            self.assertEqual(self.public.get(path).status_code, 401)
            self.assertEqual(self.authenticated(self.admin, sub="invalid").get(path).status_code, 401)
            with CaptureQueriesContext(connection) as queries:
                response = self.authenticated(self.admin, company_id=None).get(path)
            self.assertEqual(response.status_code, 403)
            self.assertFalse(any('FROM "websites"' in row["sql"] for row in queries))
        UserCompanyAccess.objects.filter(user=self.editor).delete()
        self.assertEqual(self.authenticated(self.editor).get(self.admin_url("products/")).status_code, 403)
        root = User.objects.create_user(email="root@catalog.example.test", is_superuser=True)
        self.assertEqual(self.authenticated(root).get(self.admin_url()).status_code, 200)
        self.assertEqual(self.authenticated(root, company_id=None).get(self.admin_url()).status_code, 403)

    def test_product_options_and_publication_patch_do_not_modify_or_expose_erp_masters(self):
        editor = self.authenticated(self.editor)
        options = editor.get(self.admin_url("catalog-product-options/")).json()
        self.assertEqual(options["count"], 3)
        self.assertEqual(set(options["results"][0]), {"productId", "name", "sku", "unitId", "unit"})
        self.assertNotIn(str(self.foreign.pk), json.dumps(options))
        path = self.admin_url(f"products/{self.publication.pk}/")
        for payload in ({"productId": str(self.foreign.pk)}, {"price_sale": "0.01"}, {"stock": 999}, {"company_id": str(self.b.pk)}, {"commercialTitle": "x" * 181}):
            self.assertEqual(editor.patch(path, payload, content_type="application/json", HTTP_IF_MATCH=self.etag(editor)).status_code, 400)
        self.product.refresh_from_db()
        self.assertEqual(self.product.price_sale, Decimal("999"))
        self.assertEqual(self.product.price_purchase, Decimal("555"))

    def test_overrides_are_authorized_and_inactive_defaults_produce_null(self):
        override = PriceList.objects.create(company=self.a, name="Public override", prices_include_tax=True)
        ProductPrice.objects.create(product=self.product, price_list=override, amount=7)
        result = self.client.patch(self.admin_url(f"products/{self.publication.pk}/"), {"priceListId": str(override.pk)}, content_type="application/json", HTTP_IF_MATCH=self.etag())
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(self.public.get(self.public_url(f"products/{self.product.pk}/")).json()["product"]["price"], "42.00")
        override.active = False
        override.save()
        self.assertIsNone(self.public.get(self.public_url(f"products/{self.product.pk}/")).json()["product"]["price"])
        self.configuration.default_price_list = self.foreign_list
        WebsiteCatalogSettings.objects.filter(pk=self.configuration.pk).update(default_price_list=self.foreign_list)
        self.assertIsNone(self.public.get(self.public_url(f"products/{self.second.pk}/")).json()["product"]["price"])

    def test_configured_stock_is_net_and_a_disabled_store_is_not_used(self):
        warehouse = Warehouse.objects.create(store=self.store, name="Negative warehouse A")
        StockByWarehouse.objects.create(product=self.product, warehouse=warehouse, quantity=-5)
        self.configuration.warehouses.add(warehouse)
        self.assertEqual(self.public.get(self.public_url(f"products/{self.product.pk}/")).json()["product"]["availability"], "unavailable")
        self.store.active = False
        self.store.save()
        self.assertEqual(self.public.get(self.public_url(f"products/{self.product.pk}/")).json()["product"]["availability"], "unknown")

    def test_editorial_updates_do_not_invalidate_commercial_preconditions(self):
        etag = self.etag()
        Website.objects.filter(pk=self.site.pk).update(editorial_revision=77)
        self.assertEqual(self.etag(), etag)
        result = self.patch_settings({"productsPerPage": 12}, etag=etag)
        self.assertEqual(result.status_code, 200)
        self.site.refresh_from_db()
        self.assertEqual(self.site.editorial_revision, 77)

    def test_foreign_policy_references_are_atomic_and_do_not_modify_erp(self):
        original = self.etag()
        for payload in ({"defaultPriceListId": str(self.foreign_list.pk)}, {"warehouseIds": [str(self.foreign_warehouse.pk)]}, {"warehouseIds": [str(self.warehouse.pk)] * 2}, {"productsPerPage": 0}, {"commerceEnabled": True}):
            result = self.patch_settings(payload, etag=original)
            self.assertEqual(result.status_code, 400, result.content)
            if "defaultPriceListId" in payload:
                self.assertIn("defaultPriceListId", result.json()["fields"])
            self.assertEqual(self.etag(), original)
        self.assertEqual(self.client.get(self.admin_url(website=self.foreign_site)).status_code, 404)
        UserCompanyAccess.objects.filter(user=self.admin).delete()
        self.assertEqual(self.client.get(self.admin_url()).status_code, 403)

    def test_publication_create_edit_publish_withdraw_delete_and_duplicate(self):
        editor = self.authenticated(self.editor)
        product = Product.objects.create(company=self.a, unit=self.unit, sku="NEW", name="New product")
        etag = self.etag(editor)
        created = editor.post(self.admin_url("products/"), {"productId": str(product.pk)}, content_type="application/json", HTTP_IF_MATCH=etag)
        self.assertEqual(created.status_code, 201, created.content)
        self.assertFalse(created.json()["isPublished"])
        self.assertNotIn("priceListId", created.json())
        path = self.admin_url(f"products/{created.json()['id']}/")
        response = editor.patch(path, {"isPublished": True, "commercialTitle": "Public title"}, content_type="application/json", HTTP_IF_MATCH=created["ETag"])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.public.get(self.public_url(f"products/{product.pk}/")).status_code, 200)
        duplicate = editor.post(self.admin_url("products/"), {"productId": str(product.pk)}, content_type="application/json", HTTP_IF_MATCH=response["ETag"])
        self.assertEqual(duplicate.status_code, 409)
        response = editor.patch(path, {"isPublished": False}, content_type="application/json", HTTP_IF_MATCH=response["ETag"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.public.get(self.public_url(f"products/{product.pk}/")).status_code, 404)
        deleted = editor.delete(path, HTTP_IF_MATCH=response["ETag"])
        self.assertEqual(deleted.status_code, 204)
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())
        self.assertTrue(AuditLog.objects.filter(entity="WebsiteCatalog", user=self.editor).exists())

    def test_publish_and_existing_public_edits_require_current_publish_permission(self):
        RolePermission.objects.filter(role__name="Catalog editor", permission__code="publish.website").delete()
        editor = self.authenticated(self.editor)
        etag = self.etag(editor)
        path = self.admin_url(f"products/{self.publication.pk}/")
        self.assertEqual(editor.patch(path, {"commercialTitle": "Cannot change public"}, content_type="application/json", HTTP_IF_MATCH=etag).status_code, 403)
        self.assertEqual(editor.delete(path, HTTP_IF_MATCH=etag).status_code, 403)
        self.assertEqual(editor.post(self.admin_url("products/"), {"productId": str(self.foreign.pk)}, content_type="application/json", HTTP_IF_MATCH=etag).status_code, 400)

    def test_deleting_override_list_withdraws_instead_of_falling_back_to_default(self):
        override = PriceList.objects.create(company=self.a, name="Override removed")
        self.publication.price_list = override
        self.publication.save()
        previous = self.etag()
        override.delete()
        self.publication.refresh_from_db()
        self.assertFalse(self.publication.is_published)
        self.assertEqual(self.public.get(self.public_url(f"products/{self.product.pk}/")).status_code, 404)
        self.assertNotEqual(self.etag(), previous)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_public_queries_are_bounded_and_explainable_without_n_plus_one(self):
        with CaptureQueriesContext(connection) as first:
            response = self.public.get(self.public_url())
        self.assertEqual(response.status_code, 200, response.content)
        for index in range(25):
            product = Product.objects.create(company=self.a, unit=self.unit, category=self.category, brand=self.brand, sku=f"BULK-{index}", name=f"Bulk {index}")
            WebsiteProduct.objects.create(website=self.site, product=product, is_published=True)
            ProductPrice.objects.create(product=product, price_list=self.price_list, amount=1)
        with CaptureQueriesContext(connection) as many:
            response = self.public.get(self.public_url(), {"limit": 100})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(many), len(first))
        self.assertLessEqual(len(many), 20)
        print("CATALOG_QUERY_COUNTS", json.dumps({"twoProducts": len(first), "twentySevenProducts": len(many)}))

    def test_thousand_product_query_plan_and_commercial_hash_cost(self):
        products = Product.objects.bulk_create([Product(company=self.a, unit=self.unit, category=self.category, brand=self.brand, sku=f"PROFILE-{index}", name=f"Profile {index}") for index in range(1000)])
        WebsiteProduct.objects.bulk_create([WebsiteProduct(website=self.site, product=product, slug=f"profile-{index}", is_published=True) for index, product in enumerate(products)])
        ProductPrice.objects.bulk_create([ProductPrice(product=product, price_list=self.price_list, amount=10) for product in products])
        offers = selectors.catalog_offers(self.site)
        query = selectors.order_offers(selectors.filter_offers(offers, {"min": Decimal("1")}), "price-asc")[:100]
        plan = json.loads(query.explain(format="json", analyze=True, buffers=True))[0]
        started = perf_counter()
        with CaptureQueriesContext(connection) as requests:
            response = self.public.get(self.public_url(), {"limit": 100, "min": 1, "ordering": "price-asc"})
        elapsed = (perf_counter() - started) * 1000
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["count"], 1002)
        started = perf_counter()
        services.commercial_etag(self.site)
        hash_ms = (perf_counter() - started) * 1000
        print("CATALOG_PERFORMANCE", json.dumps({"products": 1002, "pageSize": 100, "httpQueryCount": len(requests), "httpMilliseconds": round(elapsed, 2), "planExecutionMilliseconds": plan["Execution Time"], "planPlanningMilliseconds": plan["Planning Time"], "etagMilliseconds": round(hash_ms, 2), "plan": plan["Plan"]}))


@skipUnless(connection.vendor == "postgresql", "Commercial aggregate locking requires PostgreSQL")
class WebsiteCatalogConcurrencyTest(CommercialCatalogFixture, TransactionTestCase):
    def race(self, operations):
        barrier = Barrier(2)

        def write(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                operation()
                return 200
            except WebsiteError as exc:
                return exc.status
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(write, operation) for operation in operations]
            return [future.result(timeout=30) for future in futures]

    def test_same_etag_allows_only_one_commercial_writer(self):
        expected = self.etag()
        results = self.race([
            lambda: services.write_publication(user=self.editor, company_id=self.a.pk, website_id=self.site.pk, publication_id=self.publication.pk, data={"commercialTitle": "Writer A"}, expected=expected),
            lambda: services.write_publication(user=self.editor, company_id=self.a.pk, website_id=self.site.pk, publication_id=self.publication.pk, data={"commercialTitle": "Writer B"}, expected=expected),
        ])
        self.assertEqual(sorted(results), [200, 412])
        self.site.refresh_from_db()
        self.assertEqual(self.site.editorial_revision, 1)

    def test_policy_and_publication_writes_share_one_commercial_precondition(self):
        expected = self.etag()
        results = self.race([
            lambda: services.update_configuration(user=self.admin, company_id=self.a.pk, website_id=self.site.pk, data={"productsPerPage": 13}, expected=expected),
            lambda: services.write_publication(user=self.editor, company_id=self.a.pk, website_id=self.site.pk, publication_id=self.publication.pk, data={"isPublished": False}, expected=expected),
        ])
        self.assertEqual(sorted(results), [200, 412])

    def test_duplicate_creates_do_not_duplicate_erp_or_publication(self):
        product = Product.objects.create(company=self.a, unit=self.unit, sku="RACE", name="Concurrent product")
        expected = self.etag()
        def create():
            services.write_publication(user=self.editor, company_id=self.a.pk, website_id=self.site.pk, data={"productId": product.pk}, expected=expected)
        self.assertEqual(sorted(self.race([create, create])), [200, 412])
        self.assertEqual(WebsiteProduct.objects.filter(website=self.site, product=product).count(), 1)

    def test_deleting_override_concurrently_never_restores_default_price_publication(self):
        override = PriceList.objects.create(company=self.a, name="Concurrent override")
        self.publication.price_list = override
        self.publication.save()
        expected = self.etag()
        results = self.race([
            lambda: PriceList.objects.get(pk=override.pk).delete(),
            lambda: services.write_publication(user=self.editor, company_id=self.a.pk, website_id=self.site.pk, publication_id=self.publication.pk, data={"commercialTitle": "Concurrent copy"}, expected=expected),
        ])
        self.assertTrue(all(code in (200, 412) for code in results))
        self.publication.refresh_from_db()
        self.assertFalse(self.publication.is_published)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())
