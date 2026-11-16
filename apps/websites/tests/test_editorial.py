import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase, SimpleTestCase, override_settings

from apps.api.v1.auth.tokens import build_token
from django.conf import settings
from apps.companies.models import Company, UserCompanyAccess
from apps.users.models import User, Role, UserRole, RolePermission, Permission
from apps.websites.documents import normalize_document, upgrade_website_document
from apps.websites.errors import WebsiteError
from apps.websites.models import Website, WebsitePageRevision, WebsiteSettings, WebsiteSection
from apps.websites import services


def editorial_fixture():
    return json.loads((Path(__file__).parent / "fixtures/editorial-v3.json").read_text(encoding="utf-8"))


class EditorialContractTest(SimpleTestCase):
    def test_real_frontend_v3_document_roundtrips_without_loss(self):
        document = editorial_fixture()
        self.assertEqual(normalize_document(document), document)

    def test_optional_contact_and_slider_defaults_are_compatible(self):
        document = editorial_fixture()
        del document["heroSlider"]
        for field in ("email", "socials", "secondaryPhone"):
            del document["contact"][field]
        result = normalize_document(document)
        self.assertEqual(result["heroSlider"], {"autoplay": True, "intervalMs": 6000})
        self.assertEqual(result["contact"]["socials"], {})

    def test_invalid_documents_rejected_with_field_paths(self):
        mutations = [
            (lambda doc: doc.update(company_id="foreign"), "company_id"),
            (lambda doc: doc.update(schemaVersion=True), "schemaVersion"),
            (lambda doc: doc["identity"].update(name="<script>alert(1)</script>"), "identity.name"),
            (lambda doc: doc["identity"].update(primaryColor="#fff"), "identity.primaryColor"),
            (lambda doc: doc["contact"].update(email="x@example.com?bcc=a"), "contact.email"),
            (lambda doc: doc["contact"].update(socials={"x": "https://twitter.com.evil.example/user"}), "contact.socials.x"),
            (lambda doc: doc["contact"].update(socials={"x": 123}), "contact.socials.x"),
            (lambda doc: doc["banners"][0].update(href="//evil.example"), "banners.0.href"),
            (lambda doc: doc["banners"][0].update(imageUrl="data:image/png;base64,AA=="), "banners.0.imageUrl"),
            (lambda doc: doc["banners"][0].update(imageUrl="https://media.example.com:invalid/image.png"), "banners.0.imageUrl"),
            (lambda doc: doc["heroSlider"].update(intervalMs=True), "banners.intervalMs"),
            (lambda doc: doc["heroSlider"].update(intervalMs=2999), "banners.intervalMs"),
            (lambda doc: doc["sections"].append(doc["sections"][0]), "sections"),
            (lambda doc: doc["promotions"][0].update(endsAt="2026-02-30T00:00:00.000Z"), "promotions.0.endsAt"),
            (lambda doc: doc["specials"].update(productIds=["x", "x"]), "specials.productIds"),
        ]
        for mutate, expected in mutations:
            document = editorial_fixture()
            mutate(document)
            with self.subTest(field=expected), self.assertRaises(WebsiteError) as result:
                normalize_document(document)
            self.assertIn(expected, result.exception.fields)

    def test_collections_limits_and_unknown_nested_keys(self):
        for group, maximum in (("banners", 12), ("promotions", 12), ("announcements", 8)):
            document = editorial_fixture()
            collection = document[group]["items"] if group == "announcements" else document[group]
            item = collection[0]
            collection[:] = [{**item, "id": f"item-{i}"} for i in range(maximum + 1)]
            with self.subTest(group=group), self.assertRaises(WebsiteError):
                normalize_document(document)
        document = editorial_fixture()
        document["banners"][0]["onClick"] = "alert(1)"
        with self.assertRaises(WebsiteError) as result:
            normalize_document(document)
        self.assertIn("banners.0.onClick", result.exception.fields)

    def test_campaign_dates_use_exact_utc_and_order(self):
        document = editorial_fixture()
        document["promotions"][0].update(startsAt="2026-11-15T15:00:00.000Z", endsAt="2026-11-15T15:00:00.000Z")
        with self.assertRaises(WebsiteError) as result:
            normalize_document(document)
        self.assertIn("promotions.0.endsAt", result.exception.fields)

    def test_explicit_old_document_upgrade_preserves_destinations_and_content(self):
        document = editorial_fixture()
        document["schemaVersion"] = 1
        document.pop("announcements")
        document.pop("specials")
        document["sections"] = [item for item in document["sections"] if item["type"] not in ("announcements", "specials")]
        document["banners"][0]["href"] = "/catalog?category=old"
        original = deepcopy(document)
        upgraded = upgrade_website_document(document)
        self.assertEqual(document, original)
        self.assertEqual(upgraded["banners"][0]["href"], "/shop?category=old")
        self.assertEqual(upgraded["banners"][0]["title"], document["banners"][0]["title"])
        document["schemaVersion"] = 2
        self.assertEqual(upgrade_website_document(document)["banners"][0]["href"], "/catalog?category=old")

    def test_malformed_import_documents_fail_with_validation_error(self):
        for document in ({"schemaVersion": True}, {"schemaVersion": 1, "banners": {}}, {"schemaVersion": 2, "sections": [None]}):
            with self.subTest(document=document), self.assertRaises(WebsiteError):
                upgrade_website_document(document)


class EditorialTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Editorial A", ruc="20999999301")
        cls.other_company = Company.objects.create(name="Editorial B", ruc="20999999302")
        cls.website = Website.objects.create(company=cls.company, name="Web A")
        cls.other = Website.objects.create(company=cls.other_company, name="Web B")
        cls.user = User.objects.create_user(email="editorial-a@example.com")
        UserCompanyAccess.objects.create(user=cls.user, company=cls.company)
        cls.role = Role.objects.create(name="Editorial test role")
        UserRole.objects.create(user=cls.user, role=cls.role, company=cls.company)
        for code in ("read.website", "manage.website", "publish.website", "manage.website.media"):
            RolePermission.objects.create(role=cls.role, permission=Permission.objects.get(code=code))

    def setUp(self):
        self.document = editorial_fixture()
        self.token = build_token({"sub": str(self.user.pk), "type": "access", "company_id": str(self.company.pk)}, settings.JWT_ACCESS_TTL)
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {self.token}"

    def url(self, suffix, website=None):
        return f"/api/v1/websites/{(website or self.website).pk}/{suffix}/"

    def save_document(self, document=None, revision=0, **extra):
        return self.client.put(self.url("draft"), {"document": document or self.document, **extra}, content_type="application/json", HTTP_IF_MATCH=f'"{revision}"')

    def service_args(self):
        return {"user": self.user, "company_id": self.company.pk, "website_id": self.website.pk}


class EditorialPersistenceTest(EditorialTestCase):
    def test_read_initial_editor_has_no_write_side_effects(self):
        response = self.client.get(self.url("editor"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["ETag"], '"0"')
        self.assertFalse(WebsiteSettings.objects.filter(website=self.website).exists())
        self.assertFalse(WebsitePageRevision.objects.exists())
        self.assertEqual(response["Cache-Control"], "private, no-store")
        WebsiteSettings.objects.create(website=self.website, default_seo_title="SEO existente", default_seo_description="Descripción existente")
        draft = self.client.get(self.url("editor")).json()["draft"]
        self.assertEqual(draft["seo"], {"title": "SEO existente", "description": "Descripción existente"})

    def test_save_persists_all_fields_order_and_hidden_sections(self):
        self.document["banners"][0]["enabled"] = False
        self.document["sections"].reverse()
        self.document["contact"].update(secondaryPhone="1234567", email="a@example.com", socials={"x": "https://x.com/company"})
        response = self.save_document()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["ETag"], '"1"')
        self.assertEqual(response.json()["draft"], self.document)
        self.assertIsNone(response.json()["published"])
        loaded = self.client.get(self.url("editor")).json()
        self.assertEqual(loaded["draft"], self.document)
        self.assertEqual(WebsiteSection.objects.count(), 8)
        self.assertEqual(WebsiteSettings.objects.get(website=self.website).business_name, self.document["identity"]["name"])
        revision = WebsitePageRevision.objects.get()
        self.assertEqual(revision.snapshot["document"], self.document)
        self.assertEqual(revision.operation, "SAVE")
        self.assertEqual(revision.created_by, self.user)

    def test_publish_snapshot_remains_unchanged_after_later_save(self):
        self.assertEqual(self.save_document().status_code, 200)
        response = self.client.post(self.url("publish"), content_type="application/json", HTTP_IF_MATCH='"1"')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["published"], self.document)
        self.website.refresh_from_db()
        published_id = self.website.published_revision_id
        self.document["identity"]["name"] = "Nombre de borrador nuevo"
        self.document["contact"]["phone"] = "999999999"
        self.document["banners"][0]["title"] = "Banner no publicado"
        saved = self.save_document(revision=2)
        self.assertEqual(saved.status_code, 200, saved.content)
        self.assertNotEqual(saved.json()["published"]["identity"]["name"], self.document["identity"]["name"])
        self.website.refresh_from_db()
        self.assertEqual(self.website.published_revision_id, published_id)
        self.assertEqual(self.website.published_revision.operation, "PUBLISH")

    def test_restore_creates_new_draft_without_publishing(self):
        self.save_document()
        original = WebsitePageRevision.objects.get()
        self.client.post(self.url("publish"), content_type="application/json", HTTP_IF_MATCH='"1"')
        self.document["banners"][0]["title"] = "Otra versión"
        self.save_document(revision=2)
        self.client.post(self.url("publish"), content_type="application/json", HTTP_IF_MATCH='"3"')
        self.website.refresh_from_db()
        published_id = self.website.published_revision_id
        result = self.client.post(self.url("restore"), {"revisionId": str(original.pk)}, content_type="application/json", HTTP_IF_MATCH='"4"')
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()["draft"], original.snapshot["document"])
        self.assertEqual(result.json()["published"]["banners"][0]["title"], "Otra versión")
        self.website.refresh_from_db()
        self.assertEqual(self.website.published_revision_id, published_id)
        self.assertEqual(WebsitePageRevision.objects.get(operation="RESTORE").source_revision_id, original.pk)

    def test_failure_after_pointer_update_rolls_back_snapshot_and_event(self):
        self.save_document()
        self.client.post(self.url("publish"), content_type="application/json", HTTP_IF_MATCH='"1"')
        self.website.refresh_from_db()
        previous = self.website.published_revision_id
        count = WebsitePageRevision.objects.count()
        original_save = Website.save

        def fail_after_save(instance, *args, **kwargs):
            original_save(instance, *args, **kwargs)
            if "published_revision" in kwargs.get("update_fields", ()):
                raise RuntimeError("Simulated commit-path failure")

        with patch.object(Website, "save", fail_after_save), self.assertRaises(RuntimeError):
            services.publish_website(**self.service_args(), expected_revision=2)
        self.website.refresh_from_db()
        self.assertEqual(self.website.published_revision_id, previous)
        self.assertEqual(self.website.editorial_revision, 2)
        self.assertEqual(WebsitePageRevision.objects.count(), count)

    def test_revisions_are_immutable_through_model_and_queryset(self):
        self.save_document()
        revision = WebsitePageRevision.objects.get()
        for operation in (lambda: revision.save(), lambda: revision.delete(), lambda: WebsitePageRevision.objects.filter(pk=revision.pk).update(snapshot={}), lambda: WebsitePageRevision.objects.all().delete()):
            with self.assertRaises(ValidationError):
                operation()

    def test_history_is_scoped_paginated_and_has_author(self):
        self.save_document()
        self.client.post(self.url("publish"), content_type="application/json", HTTP_IF_MATCH='"1"')
        result = self.client.get(self.url("revisions"), {"limit": 1, "offset": 0}).json()
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["results"][0]["operation"], "PUBLISH")
        self.assertEqual(result["results"][0]["actor"]["id"], str(self.user.pk))
        self.assertEqual(self.client.get(self.url("revisions"), {"limit": 0}).status_code, 400)

    def test_etag_missing_stale_and_invalid_preconditions(self):
        no_header = self.client.put(self.url("draft"), {"document": self.document}, content_type="application/json")
        self.assertEqual(no_header.status_code, 428)
        self.save_document()
        self.assertEqual(self.save_document(revision=0).status_code, 412)
        for value in ('W/"1"', '*', '1', '"01"'):
            response = self.client.put(self.url("draft"), {"document": self.document}, content_type="application/json", HTTP_IF_MATCH=value)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(WebsitePageRevision.objects.count(), 1)

    def test_invalid_document_and_oversized_payload_do_not_write(self):
        self.document["banners"][0]["title"] = ""
        result = self.save_document()
        self.assertEqual(result.status_code, 400)
        self.assertIn("banners.0.title", result.json()["fields"])
        oversized = self.client.put(self.url("draft"), '{"document":"' + 'x' * (256 * 1024) + '"}', content_type="application/json", HTTP_IF_MATCH='"0"')
        self.assertEqual(oversized.status_code, 413)
        self.assertFalse(WebsitePageRevision.objects.exists())

    def test_deep_json_is_rejected_without_server_error(self):
        body = '{"document":' + '[' * 1100 + '0' + ']' * 1100 + '}'
        response = self.client.put(self.url("draft"), body, content_type="application/json", HTTP_IF_MATCH='"0"')
        self.assertEqual(response.status_code, 400)

    def test_legacy_editor_writes_cannot_bypass_etag(self):
        for path in ("/api/v1/websites/current/settings/", f"/api/v1/websites/current/pages/{self.website.pk}/sections/"):
            self.assertEqual(self.client.put(path, {}, content_type="application/json").status_code, 404)
        self.website.refresh_from_db()
        self.assertEqual(self.website.editorial_revision, 0)

    @override_settings(CORS_ALLOWED_ORIGINS=["https://editor.example"])
    def test_cors_allows_revision_header_and_exposes_etag(self):
        response = self.client.options(self.url("draft"), HTTP_ORIGIN="https://editor.example", HTTP_ACCESS_CONTROL_REQUEST_METHOD="PUT", HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,content-type,if-match")
        self.assertEqual(response.status_code, 200)
        self.assertIn("if-match", response["Access-Control-Allow-Headers"].lower())
        response = self.client.get(self.url("editor"), HTTP_ORIGIN="https://editor.example")
        self.assertIn("etag", response["Access-Control-Expose-Headers"].lower())

    def test_no_demo_product_references_are_accepted(self):
        self.document["specials"]["productIds"] = ["demo-product"]
        result = self.save_document()
        self.assertEqual(result.status_code, 400)
        self.assertFalse(WebsitePageRevision.objects.exists())

    def test_cannot_publish_unsaved_document_or_body(self):
        self.assertEqual(self.client.post(self.url("publish"), content_type="application/json", HTTP_IF_MATCH='"0"').status_code, 400)
        self.save_document()
        self.assertEqual(self.client.post(self.url("publish"), {"document": self.document}, content_type="application/json", HTTP_IF_MATCH='"1"').status_code, 400)

    def test_preview_is_authenticated_private_and_never_indexable(self):
        self.save_document()
        result = self.client.get(self.url("preview"), {"draft": "1", "source": "published"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["content"], self.document)
        self.assertIn("noindex", result["X-Robots-Tag"])
        self.client.defaults.clear()
        self.assertEqual(self.client.get(self.url("preview"), {"draft": "1"}).status_code, 401)

    def test_all_editorial_routes_reject_other_company(self):
        for suffix in ("editor", "preview", "revisions", "media"):
            self.assertEqual(self.client.get(self.url(suffix, self.other)).status_code, 404)
        self.assertEqual(self.client.put(self.url("draft", self.other), {"document": self.document}, content_type="application/json", HTTP_IF_MATCH='"0"').status_code, 404)
        self.assertEqual(self.client.post(self.url("publish", self.other), HTTP_IF_MATCH='"0"').status_code, 404)

    def test_permission_and_membership_are_revalidated(self):
        RolePermission.objects.filter(role=self.role, permission__code="publish.website").delete()
        self.save_document()
        self.assertEqual(self.client.post(self.url("publish"), content_type="application/json", HTTP_IF_MATCH='"1"').status_code, 403)
        UserCompanyAccess.objects.filter(user=self.user).delete()
        self.assertEqual(self.client.get(self.url("editor")).status_code, 403)

    def test_publisher_without_edit_grant_can_only_publish_saved_content(self):
        self.save_document()
        RolePermission.objects.filter(role=self.role, permission__code="manage.website").delete()
        response = self.client.post(self.url("publish"), content_type="application/json", HTTP_IF_MATCH='"1"')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()["capabilities"]["edit"])
        self.assertTrue(response.json()["capabilities"]["publish"])
        self.assertEqual(self.save_document(revision=2).status_code, 403)

    def test_publication_does_not_reactivate_suspended_website(self):
        self.save_document()
        Website.objects.filter(pk=self.website.pk).update(status="SUSPENDED")
        response = self.client.post(self.url("publish"), content_type="application/json", HTTP_IF_MATCH='"1"')
        self.assertEqual(response.status_code, 409)
        self.website.refresh_from_db()
        self.assertEqual(self.website.status, "SUSPENDED")
        self.assertIsNone(self.website.published_revision_id)

    def test_unconverted_legacy_blocks_are_not_silently_overwritten(self):
        from apps.websites.models import WebsitePage
        page = WebsitePage.objects.create(website=self.website, page_type="HOME", slug="home", title="Legacy")
        block = WebsiteSection.objects.create(page=page, section_type="hero.v1", position=0, config={"title": "Legacy content"})
        response = self.save_document()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "LEGACY_CONTENT_REQUIRES_MIGRATION")
        self.assertTrue(WebsiteSection.objects.filter(pk=block.pk).exists())
        self.assertFalse(WebsitePageRevision.objects.exists())

    def test_foreign_revision_is_never_restored(self):
        self.save_document()
        revision = WebsitePageRevision.objects.get()
        other_user = User.objects.create_user(email="editorial-b@example.com", is_superuser=True)
        services.save_draft(user=other_user, company_id=self.other_company.pk, website_id=self.other.pk, expected_revision=0, document=self.document)
        foreign = WebsitePageRevision.objects.exclude(pk=revision.pk).get()
        result = self.client.post(self.url("restore"), {"revisionId": str(foreign.pk)}, content_type="application/json", HTTP_IF_MATCH='"1"')
        self.assertEqual(result.status_code, 404)
        self.website.refresh_from_db()
        self.assertEqual(self.website.editorial_revision, 1)
