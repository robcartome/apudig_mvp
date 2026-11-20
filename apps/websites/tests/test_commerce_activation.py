import json
from datetime import timedelta
from uuid import uuid4
from unittest.mock import patch

from django.db import connection
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.core.models import AuditLog
from apps.partners.models import Customer
from apps.users.models import User
from apps.websites.commerce import commerce_enabled
from apps.websites.commercial_sessions import start_session
from apps.websites.models import CommercialAccount, CommercialConsent, CommercialOrderRequest, WebsiteCatalogSettings, WebsiteRegistrationQuota, WebsiteRegistrationPolicy
from apps.websites.registration_limits import client_address, consume_budget
from apps.websites.errors import WebsiteError
from .test_order_requests import OrderRequestFixture


class CommerceActivationTest(OrderRequestFixture, TestCase):
    def policy(self, client=None, data=None, etag=True):
        client = client or self.client
        url = self.admin_url()
        tag = client.get(url).headers.get("ETag")
        return client.patch(url, data or {"commerceEnabled": True}, content_type="application/json", **({"HTTP_IF_MATCH": tag} if etag else {}))

    def post_request(self, **changes):
        body = {"items": self.items, "offerFingerprint": self.fingerprint, "note": "Synthetic", "shareConfirmed": True}
        body.update(changes)
        return self.owner.post(self.base, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(self.key))

    def test_activation_requires_explicit_admin_and_preconditions(self):
        self.assertFalse(commerce_enabled(self.site.pk))
        self.assertEqual(self.policy(self.authenticated(self.editor)).status_code, 403)
        self.assertEqual(self.policy(self.authenticated(self.worker)).status_code, 403)
        self.assertEqual(self.policy(etag=False).status_code, 428)
        stale = self.client.get(self.admin_url()).headers["ETag"]
        result = self.policy()
        self.assertEqual(result.status_code, 200, result.content)
        self.assertTrue(result.json()["commerceEnabled"])
        self.assertTrue(result.json()["commerceReady"])
        self.assertEqual(self.client.patch(self.admin_url(), {"commerceEnabled": False}, content_type="application/json", HTTP_IF_MATCH=stale).status_code, 412)
        audit = AuditLog.objects.filter(action="WEBSITE_CATALOG_POLICY").latest("created_at")
        self.assertFalse(audit.meta_data["before"]["commerceEnabled"])
        self.assertTrue(audit.meta_data["after"]["commerceEnabled"])
        self.assertFalse(self.public.get(self.public_url("registration-policy/")).json()["registrationEnabled"])
        self.assertTrue(self.public.get(self.public_url("content/")).json()["commerceEnabled"])
        self.assertTrue(self.owner.get(self.base.replace("order-requests/", "")).json()["capabilities"]["prepareOrders"])
        self.assertFalse(self.public.get("/api/v1/storefront/sites/b.catalog.test/content/").json()["commerceEnabled"])

    def test_missing_policy_price_contact_and_warehouses_block_activation_atomically(self):
        WebsiteRegistrationPolicy.objects.filter(website=self.site).delete()
        result = self.policy()
        self.assertEqual(result.status_code, 409, result.content)
        self.assertIn("PRIVACY_UNAVAILABLE", result.json()["fields"])
        self.assertFalse(WebsiteCatalogSettings.objects.get(website=self.site).commerce_enabled)
        self.configuration.warehouses.clear()
        result = self.policy()
        self.assertIn("WAREHOUSES_UNAVAILABLE", result.json()["fields"])
        self.price.active = False
        self.price.save()
        self.second_publication.is_published = False
        self.second_publication.save()
        result = self.policy()
        self.assertIn("PUBLIC_OFFER_UNAVAILABLE", result.json()["fields"])

    def test_live_http_persists_idempotent_request_and_opt_out_revokes_link(self):
        self.assertEqual(self.policy().status_code, 200)
        first, replay = self.post_request(), self.post_request()
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(first.json()["id"], replay.json()["id"])
        self.assertEqual(CommercialOrderRequest.objects.count(), 1)
        self.assertTrue(first.json()["whatsappUrl"].startswith("https://wa.me/51900000001?text="))
        self.assertEqual(self.post_request(note="changed").status_code, 409)
        self.assertEqual(self.public.post(self.base, {}, content_type="application/json").status_code, 401)
        self.assertIn(self.authenticated(self.editor).post(self.base, {}, content_type="application/json").status_code, (401, 403))
        row = CommercialOrderRequest.objects.get()
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 8)
        self.assertEqual(row.status, "PREPARED")
        self.assertEqual(self.policy(data={"commerceEnabled": False}).status_code, 200)
        detail = self.owner.get(self.base + str(row.pk) + "/").json()
        self.assertIsNone(detail["whatsappUrl"])
        self.assertEqual(self.post_request().status_code, 403)
        self.assertEqual(self.owner.post(self.base + str(row.pk) + "/cancel/", {}, content_type="application/json").json()["status"], "CANCELLED")

    def test_revoked_contact_and_foreign_request_fail_closed(self):
        self.assertEqual(self.policy().status_code, 200)
        row = self.post_request().json()
        other = User.objects.create_user(email="other-order@integration.invalid")
        customer = Customer.objects.create(company=self.a, document_type="0", legal_name="Other")
        account = CommercialAccount.objects.create(user=other, customer=customer, company=self.a, verified_email=other.email, verified_at=timezone.now())
        token = start_session(other, "a.catalog.test")["access"]
        other_client = Client(HTTP_AUTHORIZATION="Bearer " + token)
        self.assertEqual(other_client.get(self.base + row["id"] + "/").status_code, 404)
        CommercialAccount.objects.filter(pk=self.account.pk).update(status="SUSPENDED")
        self.assertIn(self.post_request().status_code, (401, 403))

    def test_effective_capability_fails_closed_after_readiness_loss(self):
        self.assertEqual(self.policy().status_code, 200)
        WebsiteRegistrationPolicy.objects.filter(website=self.site).delete()
        self.assertFalse(commerce_enabled(self.site.pk))
        self.assertEqual(self.post_request().status_code, 403)
        # Rollback/disable remains possible without readiness.
        self.assertEqual(self.policy(data={"commerceEnabled": False}).status_code, 200)


class RegistrationLimitsTest(TestCase):
    @override_settings(WEBSITE_REGISTRATION_IP_LIMIT=2)
    def test_shared_database_budget_rejects_abuse_and_keeps_only_hashes(self):
        consume_budget("a.test", "first@test.invalid", "192.0.2.1")
        consume_budget("b.test", "second@test.invalid", "192.0.2.1")
        with self.assertRaises(WebsiteError) as error:
            consume_budget("c.test", "third@test.invalid", "192.0.2.1")
        self.assertEqual(error.exception.status, 429)
        for key in WebsiteRegistrationQuota.objects.values_list("key", flat=True):
            self.assertRegex(key, r"^[0-9a-f]{40}$")
        self.assertEqual(WebsiteRegistrationQuota.objects.count(), 6)

    @override_settings(WEBSITE_TRUSTED_PROXY_CIDRS=("192.0.2.0/24",))
    def test_forwarded_ip_only_uses_explicit_trusted_chain(self):
        self.assertEqual(client_address({"REMOTE_ADDR": "198.51.100.1", "HTTP_X_FORWARDED_FOR": "203.0.113.1"}), "198.51.100.1")
        self.assertEqual(client_address({"REMOTE_ADDR": "192.0.2.1", "HTTP_X_FORWARDED_FOR": "203.0.113.99, 198.51.100.1, 192.0.2.2"}), "198.51.100.1")
        self.assertEqual(client_address({"REMOTE_ADDR": "192.0.2.1", "HTTP_X_FORWARDED_FOR": "malformed"}), "192.0.2.1")


class CommerceMigrationTest(OrderRequestFixture, TransactionTestCase):
    def test_additive_migration_reverse_preserves_erp_and_requests_and_old_public_reads(self):
        row = self.prepare()
        from apps.companies.models import Company
        from apps.inventory.models import Product
        counts = (Company.objects.count(), Product.objects.count(), CommercialAccount.objects.count())
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate([("websites", "0013_commercial_order_requests")])
            # Current public code is also safe before the additive column exists.
            response = self.public.get(self.public_url("content/"))
            self.assertEqual(response.status_code, 200, response.content)
            self.assertFalse(response.json()["commerceEnabled"])
            self.assertEqual(self.public.get(self.public_url("products/")).status_code, 200)
            self.assertEqual((Company.objects.count(), Product.objects.count(), CommercialAccount.objects.count()), counts)
            self.assertTrue(CommercialOrderRequest.objects.filter(pk=row.pk).exists())
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
        self.assertFalse(WebsiteCatalogSettings.objects.get(website=self.site).commerce_enabled)
        self.assertTrue(CommercialOrderRequest.objects.filter(pk=row.pk).exists())
        # Old code creating settings after the additive migration gets DB false.
        old_state = executor.loader.project_state(latest)
        old_state.remove_field("websites", "websitecatalogsettings", "commerce_enabled")
        old_apps = old_state.apps
        old_model = old_apps.get_model("websites", "WebsiteCatalogSettings")
        old_model.objects.create(website_id=self.foreign_site.pk)
        self.assertFalse(WebsiteCatalogSettings.objects.get(website=self.foreign_site).commerce_enabled)
