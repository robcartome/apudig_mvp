from django.test import Client
from django.utils import timezone
from apps.websites.errors import WebsiteError
from apps.websites.models import Website, WebsiteDomain
from apps.websites.storage_keys import build_website_media_key, owns_media_key
from .test_editorial import EditorialTestCase


class PublishedContentTest(EditorialTestCase):
    def setUp(self):
        super().setUp()
        self.public = Client()
        WebsiteDomain.objects.create(website=self.website, hostname="a.b3.test", status="ACTIVE", verified_at=timezone.now(), is_primary=True)
        WebsiteDomain.objects.create(website=self.other, hostname="b.b3.test", status="ACTIVE", verified_at=timezone.now(), is_primary=True)

    def publish(self):
        self.assertEqual(self.save_document().status_code, 200)
        self.assertEqual(self.client.post(self.url("publish"), {}, content_type="application/json", HTTP_IF_MATCH='"1"').status_code, 200)

    def content(self, hostname="a.b3.test", **headers):
        return self.public.get(f"/api/v1/storefront/sites/{hostname}/content/", **headers)

    def test_publication_is_single_snapshot_and_draft_is_private(self):
        self.assertEqual(self.content().status_code, 404)
        self.publish()
        previous = self.content().json()
        self.document["identity"]["name"] = "Private draft title"
        self.assertEqual(self.save_document(revision=2).status_code, 200)
        self.assertEqual(self.content().json(), previous)
        self.assertEqual(self.client.post(self.url("publish"), {}, content_type="application/json", HTTP_IF_MATCH='"3"').status_code, 200)
        self.assertEqual(self.content().json()["content"]["identity"]["name"], "Private draft title")

    def test_projection_excludes_hidden_content_private_fields_and_commerce(self):
        self.document["banners"][0].update(enabled=False, title="Hidden banner marker")
        self.document["sections"][0].update(enabled=False, title="Hidden section marker")
        self.document["announcements"]["items"][0].update(enabled=False, title="Hidden notice marker")
        self.publish()
        response = self.content()
        self.assertEqual(response.status_code, 200)
        text = response.content.decode()
        for marker in ("Hidden banner marker", "Hidden section marker", "Hidden notice marker", "companyId", "storage_key", '"draft"', '"events"', '"actor"'):
            self.assertNotIn(marker, text)
        self.assertFalse(response.json()["commerceEnabled"])
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_unknown_inactive_and_other_tenants_never_fall_back(self):
        self.publish()
        for host in ("unknown.b3.test", "b.b3.test", "127.0.0.1", "a.b3.test:8000"):
            self.assertEqual(self.content(host).status_code, 404)
        WebsiteDomain.objects.filter(website=self.website).update(status="DISABLED", is_primary=False)
        self.assertEqual(self.content().status_code, 404)

    def test_forwarded_headers_cannot_select_another_site(self):
        self.publish()
        response = self.content("unknown.b3.test", HTTP_X_FORWARDED_HOST="a.b3.test", HTTP_X_COMPANY_ID=str(self.company.pk))
        self.assertEqual(response.status_code, 404)
        resolve = self.public.get("/api/v1/storefront/resolve/?hostname=A.B3.TEST.")
        self.assertEqual(resolve.status_code, 200)
        self.assertEqual(resolve.json()["hostname"], "a.b3.test")
        self.assertNotIn("content", resolve.json())

    def test_discovery_rejects_company_domain_mismatch(self):
        response = self.client.get("/api/v1/websites/current/?hostname=b.b3.test")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "DOMAIN_COMPANY_MISMATCH")

    def test_suspended_site_and_inactive_company_are_not_public(self):
        self.publish()
        Website.objects.filter(pk=self.website.pk).update(status="SUSPENDED")
        self.assertEqual(self.content().status_code, 404)
        Website.objects.filter(pk=self.website.pk).update(status="PUBLISHED")
        self.company.is_active = False
        self.company.save()
        self.assertEqual(self.content().status_code, 404)

    def test_media_namespaces_are_separate_and_legacy_remains_readable(self):
        key = build_website_media_key(self.website, "BANNER", "unique-id")
        self.assertTrue(key.startswith(f"companies/{self.company.pk}/website/banners/"))
        self.assertTrue(owns_media_key(self.website, key))
        self.assertFalse(owns_media_key(self.other, key))
        self.assertTrue(owns_media_key(self.website, f"websites/{self.website.pk}/media/old.webp"))
        self.website.storage_prefix = "ft_soledad"
        self.assertEqual(build_website_media_key(self.website, "LOGO", "new-id"), "ft_soledad/website/logo/new-id")
        self.website.storage_prefix = "../foreign"
        with self.assertRaises(WebsiteError):
            build_website_media_key(self.website, "IMAGE", "new-id")

    def test_categories_are_allowlisted(self):
        for kind in ("IMAGE", "LOGO", "BANNER", "PROMOTION", "SECTION", "FAVICON"):
            self.assertIn("/website/", build_website_media_key(self.website, kind, "id"))
        with self.assertRaises(WebsiteError):
            build_website_media_key(self.website, "../products", "id")

    def test_expired_promotions_and_hidden_notices_are_not_public(self):
        self.document["promotions"][0].update(startsAt="2020-01-01T00:00:00.000Z", endsAt="2020-01-02T00:00:00.000Z", title="Expired promotion marker")
        for section in self.document["sections"]:
            if section["type"] == "announcements":
                section["enabled"] = False
        self.publish()
        data = self.content().json()["content"]
        self.assertEqual(data["promotions"], [])
        self.assertEqual(data["announcements"]["items"], [])
