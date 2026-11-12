from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.api.v1.auth.tokens import build_token
from apps.api.v1.users.helpers import make_token_pair
from apps.companies.models import Company, UserCompanyAccess
from apps.companies.models import Store
from apps.inventory.models import PriceList, Product, Unit, Warehouse
from apps.users.models import Permission, Role, RolePermission, User, UserRole
from apps.websites.models import Website, WebsiteDomain, WebsiteMedia, WebsiteMenu, WebsitePage, WebsitePageRevision
from apps.websites.services import revalidation_payload


class WebsiteFoundationAPITest(TestCase):
    def setUp(self):
        permission_definitions = (
            ("read.website", "read", "website"),
            ("manage.website", "manage", "website"),
            ("publish.website", "manage", "website.publish"),
            ("manage.website.domains", "manage", "website.domains"),
            ("manage.website.media", "manage", "website.media"),
        )
        for code, action_name, module in permission_definitions:
            Permission.objects.update_or_create(
                code=code,
                defaults={"action_name": action_name, "module": module},
            )

        self.company_a = Company.objects.create(name="Empresa A", ruc="20111111111")
        self.company_b = Company.objects.create(name="Empresa B", ruc="20222222222")
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
        self.domain_a = WebsiteDomain.objects.create(
            website=self.website_a,
            hostname="a.apudig.test",
            kind=WebsiteDomain.Kind.CUSTOM,
            status=WebsiteDomain.Status.ACTIVE,
            is_primary=True,
            verified_at=timezone.now(),
        )
        self.domain_b = WebsiteDomain.objects.create(
            website=self.website_b,
            hostname="b.apudig.test",
            kind=WebsiteDomain.Kind.CUSTOM,
            status=WebsiteDomain.Status.ACTIVE,
            is_primary=True,
            verified_at=timezone.now(),
        )

        self.user_a = User.objects.create_user(email="manager-a@test.com", password="pass")
        self.access_a = UserCompanyAccess.objects.create(
            user=self.user_a,
            company=self.company_a,
            store=None,
            is_default=True,
        )
        self.manager_role = Role.objects.create(name="WEBSITE_MANAGER_TEST")
        for permission in Permission.objects.filter(
            code__in=("read.website", "manage.website", "manage.website.domains", "manage.website.media")
        ):
            RolePermission.objects.create(role=self.manager_role, permission=permission)
        UserRole.objects.create(
            user=self.user_a,
            company=self.company_a,
            role=self.manager_role,
        )
        self.token_a = make_token_pair(self.user_a, self.access_a)["access"]
        self.generic_token = make_token_pair(self.user_a, None)["access"]
        self.forged_b_token = build_token(
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

        self.reader = User.objects.create_user(email="reader-a@test.com", password="pass")
        reader_access = UserCompanyAccess.objects.create(
            user=self.reader,
            company=self.company_a,
            store=None,
        )
        reader_role = Role.objects.create(name="WEBSITE_READER_TEST")
        RolePermission.objects.create(
            role=reader_role,
            permission=Permission.objects.get(code="read.website"),
        )
        UserRole.objects.create(user=self.reader, company=self.company_a, role=reader_role)
        self.reader_token = make_token_pair(self.reader, reader_access)["access"]

        self.publisher = User.objects.create_user(email="publisher-a@test.com", password="pass")
        publisher_access = UserCompanyAccess.objects.create(user=self.publisher, company=self.company_a, store=None)
        publisher_role = Role.objects.create(name="WEBSITE_PUBLISHER_TEST")
        for permission in Permission.objects.filter(code__in=("read.website", "manage.website", "publish.website")):
            RolePermission.objects.create(role=publisher_role, permission=permission)
        UserRole.objects.create(user=self.publisher, company=self.company_a, role=publisher_role)
        self.publisher_token = make_token_pair(self.publisher, publisher_access)["access"]

    @staticmethod
    def auth(token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_current_website_is_scoped_to_token_company(self):
        response = self.client.get(
            "/api/v1/websites/current/",
            **self.auth(self.token_a),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(self.website_a.pk))
        self.assertEqual(response.json()["template_key"], "ecommerce")
        self.assertEqual(response.json()["template_schema_version"], 1)
        self.assertNotIn("company", response.json())

    def test_domain_context_rejects_another_company(self):
        own = self.client.get(
            "/api/v1/websites/current/domain-context/", {"hostname": self.domain_a.hostname},
            **self.auth(self.token_a),
        )
        foreign = self.client.get(
            "/api/v1/websites/current/domain-context/", {"hostname": self.domain_b.hostname},
            **self.auth(self.token_a),
        )
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.json()["website_id"], str(self.website_a.pk))
        self.assertEqual(foreign.status_code, 404)

    def test_template_cannot_change_through_general_website_patch(self):
        response = self.client.patch(
            "/api/v1/websites/current/", {"template_key": "corporate"},
            content_type="application/json", **self.auth(self.token_a),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["template_key"], "ecommerce")

    def test_publication_state_cannot_change_through_general_page_patch(self):
        home = WebsitePage.objects.get(website=self.website_a, page_type=WebsitePage.PageType.HOME)
        response = self.client.patch(
            f"/api/v1/websites/current/pages/{home.pk}/",
            {
                "status": WebsitePage.Status.PUBLISHED,
                "draft_version": 99,
                "published_version": 99,
                "published_at": timezone.now().isoformat(),
            },
            content_type="application/json",
            **self.auth(self.token_a),
        )
        self.assertEqual(response.status_code, 200)
        home.refresh_from_db()
        self.assertEqual(home.status, WebsitePage.Status.DRAFT)
        self.assertEqual(home.draft_version, 1)
        self.assertEqual(home.published_version, 0)
        self.assertIsNone(home.published_at)

    def test_home_rejects_duplicate_singleton_and_standard_rejects_home_only(self):
        home = WebsitePage.objects.get(website=self.website_a, page_type=WebsitePage.PageType.HOME)
        standard = WebsitePage.objects.create(website=self.website_a, title="Nosotros", slug="nosotros")
        duplicate = self.client.put(
            f"/api/v1/websites/current/pages/{home.pk}/sections/",
            {"expected_version": 1, "sections": [
                {"section_type": "hero.v1", "schema_version": 1, "position": 0, "config": {"title": "Uno"}},
                {"section_type": "hero.v1", "schema_version": 1, "position": 1, "config": {"title": "Dos"}},
            ]}, content_type="application/json", **self.auth(self.token_a),
        )
        self.assertEqual(duplicate.status_code, 400)
        foreign_slot = self.client.put(
            f"/api/v1/websites/current/pages/{standard.pk}/sections/",
            {"expected_version": 1, "sections": [
                {"section_type": "categories.v1", "schema_version": 1, "position": 0, "config": {"title": "Categorías"}},
            ]}, content_type="application/json", **self.auth(self.token_a),
        )
        self.assertEqual(foreign_slot.status_code, 400)

    def test_token_without_authorized_company_is_denied(self):
        missing = self.client.get(
            "/api/v1/websites/current/",
            **self.auth(self.generic_token),
        )
        forged = self.client.get(
            "/api/v1/websites/current/",
            **self.auth(self.forged_b_token),
        )
        self.assertEqual(missing.status_code, 403)
        self.assertEqual(forged.status_code, 403)

    def test_reader_can_read_but_cannot_update(self):
        read = self.client.get(
            "/api/v1/websites/current/",
            **self.auth(self.reader_token),
        )
        update = self.client.patch(
            "/api/v1/websites/current/",
            {"name": "No autorizado"},
            content_type="application/json",
            **self.auth(self.reader_token),
        )
        self.assertEqual(read.status_code, 200)
        self.assertEqual(update.status_code, 403)

    def test_manager_updates_only_current_company_website(self):
        response = self.client.patch(
            "/api/v1/websites/current/",
            {"name": "Tienda A actualizada", "currency": "pen"},
            content_type="application/json",
            **self.auth(self.token_a),
        )
        self.assertEqual(response.status_code, 200)
        self.website_a.refresh_from_db()
        self.website_b.refresh_from_db()
        self.assertEqual(self.website_a.name, "Tienda A actualizada")
        self.assertEqual(self.website_a.currency, "PEN")
        self.assertEqual(self.website_b.name, "Tienda B")

    def test_settings_update_is_tenant_scoped(self):
        response = self.client.patch(
            "/api/v1/websites/current/settings/",
            {"business_name": "Ferreteria A", "primary_color": "#123456"},
            content_type="application/json",
            **self.auth(self.token_a),
        )
        self.assertEqual(response.status_code, 200)
        self.website_a.settings.refresh_from_db()
        self.website_b.settings.refresh_from_db()
        self.assertEqual(self.website_a.settings.business_name, "Ferreteria A")
        self.assertEqual(self.website_b.settings.business_name, "Tienda B")

    def test_domain_registration_is_pending_and_hashes_one_time_token(self):
        response = self.client.post(
            "/api/v1/websites/current/domains/",
            {"hostname": "tienda-a.example.com", "kind": "CUSTOM"},
            content_type="application/json",
            **self.auth(self.token_a),
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        token = payload["verification_token"]
        domain = WebsiteDomain.objects.get(hostname="tienda-a.example.com")
        self.assertEqual(domain.website_id, self.website_a.pk)
        self.assertEqual(domain.status, WebsiteDomain.Status.PENDING)
        self.assertFalse(domain.is_primary)
        self.assertTrue(domain.verification_token_hash)
        self.assertNotEqual(domain.verification_token_hash, token)

        listed = self.client.get(
            "/api/v1/websites/current/domains/",
            **self.auth(self.token_a),
        )
        listed_payload = listed.json()
        listed_items = listed_payload.get("results", listed_payload)
        created = next(item for item in listed_items if item["id"] == str(domain.pk))
        self.assertNotIn("verification_token", created)

    def test_duplicate_and_reserved_domains_are_rejected(self):
        duplicate = self.client.post(
            "/api/v1/websites/current/domains/",
            {"hostname": self.domain_b.hostname, "kind": "CUSTOM"},
            content_type="application/json",
            **self.auth(self.token_a),
        )
        reserved = self.client.post(
            "/api/v1/websites/current/domains/",
            {"hostname": "web.apudig.com", "kind": "SUBDOMAIN"},
            content_type="application/json",
            **self.auth(self.token_a),
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(reserved.status_code, 400)

    def test_public_resolve_returns_identity_without_internal_company(self):
        self.website_a.settings.business_name = "Ferreteria A"
        self.website_a.settings.address = "Huaraz"
        self.website_a.settings.save()
        response = self.client.get(
            "/api/v1/storefront/resolve/",
            {"hostname": self.domain_a.hostname},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["name"], "Ferreteria A")
        self.assertEqual(payload["canonical_url"], "https://a.apudig.test")
        self.assertEqual(payload["contact"]["address"], "Huaraz")
        self.assertNotIn("company_id", payload)
        self.assertTrue(response["X-Request-ID"])

    def create_page(self, token=None, title="Nosotros", slug="nosotros"):
        response = self.client.post(
            "/api/v1/websites/current/pages/",
            {"title": title, "slug": slug, "page_type": "STANDARD"},
            content_type="application/json", **self.auth(token or self.token_a),
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def replace_sections(self, page, sections, token=None, expected_version=None):
        return self.client.put(
            f"/api/v1/websites/current/pages/{page['id']}/sections/",
            {"expected_version": expected_version or page["draft_version"], "sections": sections},
            content_type="application/json", **self.auth(token or self.token_a),
        )

    def test_editor_can_edit_but_cannot_publish(self):
        page = self.create_page()
        edited = self.replace_sections(page, [{
            "section_type": "hero.v1", "schema_version": 1, "position": 0,
            "enabled": True, "config": {"title": "Hola"},
        }])
        self.assertEqual(edited.status_code, 200, edited.content)
        denied = self.client.post(
            f"/api/v1/websites/current/pages/{page['id']}/publish/",
            {"expected_version": edited.json()["draft_version"]}, content_type="application/json",
            **self.auth(self.token_a),
        )
        self.assertEqual(denied.status_code, 403)

    def test_draft_is_not_public_and_publish_creates_immutable_snapshot(self):
        page = self.create_page(token=self.publisher_token)
        draft_public = self.client.get(f"/api/v1/storefront/sites/{self.domain_a.hostname}/pages/nosotros/")
        self.assertEqual(draft_public.status_code, 404)
        edited = self.replace_sections(page, [{
            "section_type": "hero.v1", "schema_version": 1, "position": 0,
            "enabled": True, "config": {"title": "Versión pública"},
        }], token=self.publisher_token).json()
        published = self.client.post(
            f"/api/v1/websites/current/pages/{page['id']}/publish/",
            {"expected_version": edited["draft_version"]}, content_type="application/json",
            **self.auth(self.publisher_token),
        )
        self.assertEqual(published.status_code, 200, published.content)
        self.assertEqual(WebsitePageRevision.objects.get(page_id=page["id"]).snapshot["sections"][0]["config"]["title"], "Versión pública")

        changed = self.replace_sections(edited, [{
            "section_type": "hero.v1", "schema_version": 1, "position": 0,
            "enabled": True, "config": {"title": "Cambio sin publicar"},
        }], token=self.publisher_token).json()
        self.assertGreater(changed["draft_version"], edited["draft_version"])
        public = self.client.get(f"/api/v1/storefront/sites/{self.domain_a.hostname}/pages/nosotros/")
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.json()["sections"][0]["config"]["title"], "Versión pública")

        restored = self.client.post(
            f"/api/v1/websites/current/pages/{page['id']}/revisions/1/restore/",
            {"expected_version": changed["draft_version"]}, content_type="application/json",
            **self.auth(self.publisher_token),
        )
        self.assertEqual(restored.status_code, 200, restored.content)
        self.assertEqual(restored.json()["sections"][0]["config"]["title"], "Versión pública")
        self.assertEqual(restored.json()["published_version"], 1)
        self.assertEqual(WebsitePageRevision.objects.get(page_id=page["id"], version=1).snapshot["sections"][0]["config"]["title"], "Versión pública")

    def test_invalid_block_order_conflict_and_cross_tenant_id_are_rejected(self):
        page = self.create_page()
        invalid = self.replace_sections(page, [{
            "section_type": "hero.v1", "schema_version": 1, "position": 0,
            "enabled": True, "config": {"title": "<script>alert(1)</script>"},
        }])
        self.assertEqual(invalid.status_code, 400)
        ordered = self.replace_sections(page, [
            {"section_type": "hero.v1", "schema_version": 1, "position": 0, "enabled": True, "config": {"title": "Primero"}},
            {"section_type": "contact.v1", "schema_version": 1, "position": 1, "enabled": False, "config": {"title": "Segundo"}},
        ])
        self.assertEqual(ordered.status_code, 200, ordered.content)
        self.assertEqual([item["position"] for item in ordered.json()["sections"]], [0, 1])
        self.assertFalse(ordered.json()["sections"][1]["enabled"])
        conflict = self.replace_sections(page, [], expected_version=page["draft_version"])
        self.assertEqual(conflict.status_code, 409)
        foreign_page = WebsitePage.objects.create(website=self.website_b, title="Privada", slug="privada")
        foreign = self.client.get(f"/api/v1/websites/current/pages/{foreign_page.pk}/", **self.auth(self.token_a))
        self.assertEqual(foreign.status_code, 404)

    def test_preview_token_is_version_bound_and_revalidation_tags_are_tenant_specific(self):
        page = self.create_page()
        token_response = self.client.post(
            f"/api/v1/websites/current/pages/{page['id']}/preview-token/", **self.auth(self.token_a)
        )
        self.assertEqual(token_response.status_code, 200)
        preview = self.client.get(
            f"/api/v1/storefront/sites/{self.domain_a.hostname}/pages/nosotros/",
            {"preview_token": token_response.json()["token"]},
        )
        self.assertEqual(preview.status_code, 200)
        model = WebsitePage.objects.get(pk=page["id"])
        self.assertEqual(revalidation_payload(model)["tags"], [
            f"site:{self.website_a.pk}", f"page:{self.website_a.pk}:nosotros",
            f"host:{self.domain_a.hostname}", f"page-host:{self.domain_a.hostname}:nosotros",
        ])

    def test_media_library_and_theme_reject_cross_tenant_media(self):
        media_a = WebsiteMedia.objects.create(
            website=self.website_a, storage_key="websites/a/logo.webp", original_name="logo-a.png",
            checksum="a" * 64, width=100, height=100,
        )
        media_b = WebsiteMedia.objects.create(
            website=self.website_b, storage_key="websites/b/logo.webp", original_name="logo-b.png",
            checksum="b" * 64, width=100, height=100,
        )
        listed = self.client.get("/api/v1/websites/current/media/", **self.auth(self.token_a))
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([item["id"] for item in listed.json()], [str(media_a.pk)])
        crossed = self.client.patch(
            "/api/v1/websites/current/settings/", {"logo_media": str(media_b.pk)},
            content_type="application/json", **self.auth(self.token_a),
        )
        self.assertEqual(crossed.status_code, 400)
        accepted = self.client.patch(
            "/api/v1/websites/current/settings/", {"logo_media": str(media_a.pk), "heading_font": "serif"},
            content_type="application/json", **self.auth(self.token_a),
        )
        self.assertEqual(accepted.status_code, 200, accepted.content)
        self.assertEqual(accepted.json()["logo_media_url"], media_a.url)

    def test_menu_draft_requires_publish_permission_and_public_uses_snapshot(self):
        menu = WebsiteMenu.objects.get(website=self.website_a, location=WebsiteMenu.Location.HEADER)
        home = WebsitePage.objects.get(website=self.website_a, page_type=WebsitePage.PageType.HOME)
        replaced = self.client.put(
            f"/api/v1/websites/current/menus/{menu.pk}/items/",
            {"expected_version": menu.draft_version, "items": [{
                "parent_index": None, "position": 0, "label": "Inicio",
                "target_type": "PAGE", "page_id": str(home.pk), "enabled": True,
            }]}, content_type="application/json", **self.auth(self.token_a),
        )
        self.assertEqual(replaced.status_code, 200, replaced.content)
        denied = self.client.post(
            f"/api/v1/websites/current/menus/{menu.pk}/publish/",
            {"expected_version": replaced.json()["draft_version"]},
            content_type="application/json", **self.auth(self.token_a),
        )
        self.assertEqual(denied.status_code, 403)
        published = self.client.post(
            f"/api/v1/websites/current/menus/{menu.pk}/publish/",
            {"expected_version": replaced.json()["draft_version"]},
            content_type="application/json", **self.auth(self.publisher_token),
        )
        self.assertEqual(published.status_code, 200, published.content)
        resolved = self.client.get("/api/v1/storefront/resolve/", {"hostname": self.domain_a.hostname})
        self.assertEqual(resolved.json()["menus"]["header"][0]["href"], "/")

    def test_primary_domain_controls_canonical_and_manifest_is_tenant_scoped(self):
        alias = WebsiteDomain.objects.create(
            website=self.website_a, hostname="alias-a.apudig.test", kind=WebsiteDomain.Kind.ALIAS,
            status=WebsiteDomain.Status.ACTIVE, verified_at=timezone.now(),
        )
        primary = self.client.patch(
            f"/api/v1/websites/current/domains/{alias.pk}/primary/", {},
            content_type="application/json", **self.auth(self.token_a),
        )
        self.assertEqual(primary.status_code, 200, primary.content)
        self.domain_a.refresh_from_db()
        self.assertFalse(self.domain_a.is_primary)
        resolved = self.client.get("/api/v1/storefront/resolve/", {"hostname": self.domain_a.hostname})
        self.assertEqual(resolved.json()["canonical_hostname"], alias.hostname)
        self.assertFalse(resolved.json()["is_primary"])
        manifest = self.client.get(f"/api/v1/storefront/sites/{self.domain_a.hostname}/manifest/")
        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(manifest.json()["canonical_url"], f"https://{alias.hostname}")

    def test_catalog_management_rejects_cross_tenant_sources_and_controls_publication(self):
        unit = Unit.objects.create(code="NIU", name="Unidad")
        product_a = Product.objects.create(
            company=self.company_a, name="Producto A", sku="WEB-A", unit=unit,
            price_sale="25.00",
        )
        product_b = Product.objects.create(
            company=self.company_b, name="Producto B", sku="WEB-B", unit=unit,
            price_sale="35.00",
        )
        price_b = PriceList.objects.create(company=self.company_b, name="Lista B")
        store_b = Store.objects.create(company=self.company_b, name="Local B")
        warehouse_b = Warehouse.objects.create(store=store_b, name="Almacén B")

        crossed_settings = self.client.patch(
            "/api/v1/websites/current/catalog-settings/",
            {"default_price_list": str(price_b.pk), "warehouses": [str(warehouse_b.pk)]},
            content_type="application/json", **self.auth(self.token_a),
        )
        self.assertEqual(crossed_settings.status_code, 400)

        crossed_product = self.client.post(
            "/api/v1/websites/current/products/",
            {"product": str(product_b.pk), "is_published": True},
            content_type="application/json", **self.auth(self.token_a),
        )
        self.assertEqual(crossed_product.status_code, 400)

        draft = self.client.post(
            "/api/v1/websites/current/products/",
            {"product": str(product_a.pk), "is_published": False},
            content_type="application/json", **self.auth(self.token_a),
        )
        self.assertEqual(draft.status_code, 201, draft.content)
        hidden = self.client.get(
            f"/api/v1/storefront/sites/{self.domain_a.hostname}/products/"
        )
        self.assertEqual(hidden.json()["total"], 0)

        denied = self.client.patch(
            f"/api/v1/websites/current/products/{draft.json()['id']}/",
            {"is_published": True}, content_type="application/json",
            **self.auth(self.token_a),
        )
        self.assertEqual(denied.status_code, 403)

        published = self.client.patch(
            f"/api/v1/websites/current/products/{draft.json()['id']}/",
            {"is_published": True}, content_type="application/json",
            **self.auth(self.publisher_token),
        )
        self.assertEqual(published.status_code, 200, published.content)
        visible = self.client.get(
            f"/api/v1/storefront/sites/{self.domain_a.hostname}/products/"
        )
        self.assertEqual([item["id"] for item in visible.json()["results"]], [str(product_a.pk)])
