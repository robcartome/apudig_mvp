from copy import deepcopy
from datetime import timedelta
from uuid import uuid4
from django.test import Client, TestCase
from django.utils import timezone

from apps.users.models import User
from apps.partners.models import Customer
from apps.websites.accounts import issue_email_challenge, verify_email_challenge
from apps.websites.catalog.quotation import recalculate_commercial_cart
from apps.websites.commercial_sessions import start_session
from apps.websites.errors import WebsiteError
from apps.websites.models import CommercialAccount, CommercialConsent, CommercialOrderRequest, WebsitePageRevision
from apps.websites.registration import configure_notice, policy_etag
from apps.websites import order_requests as services
from .test_catalog import CommercialCatalogFixture


class OrderRequestFixture(CommercialCatalogFixture):
    def setUp(self):
        super().setUp()
        self.person = User.objects.create_user(email="requester@integration.invalid")
        self.customer = Customer.objects.create(company=self.a, document_type="0", legal_name="Request owner")
        self.account = CommercialAccount.objects.create(user=self.person, company=self.a, customer=self.customer)
        self.notice = configure_notice(user=self.admin, company_id=self.a.pk, website_id=self.site.pk, version="synthetic-v1", text="Synthetic fixture only; not an approved production privacy notice.", pending_retention_days=3, linking_mode="NEW_OR_REVIEW", expected=policy_etag(None))
        CommercialConsent.objects.create(user=self.person, notice=self.notice, accepted_at=timezone.now())
        verify_email_challenge(self.person, self.site, issue_email_challenge(self.person, self.site))
        previous = self.site.published_revision
        snapshot = deepcopy(previous.snapshot)
        snapshot["document"]["contact"]["whatsapp"] = "51900000001"
        previous.page.published_version = previous.page.draft_version = 2
        previous.page.save(update_fields=["published_version", "draft_version"])
        self.site.published_revision = WebsitePageRevision.objects.create(page=previous.page, version=2, operation="PUBLISH", editorial_revision=2, snapshot=snapshot)
        self.site.editorial_revision = 2
        self.site.save(update_fields=["published_revision", "editorial_revision"])
        self.items = [{"productId": str(self.product.pk), "unitId": str(self.unit.pk), "quantity": 1}]
        self.fingerprint = recalculate_commercial_cart(self.person, "a.catalog.test", self.items)["offerFingerprint"]
        self.key = uuid4()
        tokens = start_session(self.person, "a.catalog.test")
        self.owner = Client(HTTP_AUTHORIZATION="Bearer " + tokens["access"])
        self.base = "/api/v1/storefront/sites/a.catalog.test/account/order-requests/"

    def prepare(self, **changes):
        args = dict(user=self.person, hostname="a.catalog.test", items=self.items, offer_fingerprint=self.fingerprint, note="Synthetic note", idempotency_key=self.key, share_confirmed=True)
        args.update(changes)
        return services.prepare_request(**args)


class OrderRequestTest(OrderRequestFixture, TestCase):
    def test_domain_engine_prepares_one_expiring_intent_without_reserving_stock(self):
        # Domain-only: the public POST gate is closed and is tested separately.
        row = self.prepare()
        self.assertEqual(self.prepare().pk, row.pk)
        self.assertEqual(CommercialOrderRequest.objects.count(), 1)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 8)
        self.assertEqual(services.request_data(row)["status"], "PREPARED")
        self.assertIsNone(services.request_data(row)["whatsappUrl"])
        # Formatting a synthetic link is not sending a message or receiving an order.
        link = services.request_data(row, allow_whatsapp=True)["whatsappUrl"]
        self.assertTrue(link.startswith("https://wa.me/51900000001?text="))
        row.refresh_from_db()
        self.assertEqual(row.status, "PREPARED")
        self.assertNotIn(self.person.email, link)

    def test_same_key_different_body_and_changed_price_require_new_review(self):
        self.prepare()
        with self.assertRaises(WebsiteError) as conflict:
            self.prepare(note="Different body")
        self.assertEqual(conflict.exception.code, "IDEMPOTENCY_CONFLICT")
        self.price.amount = "12"
        self.price.save()
        with self.assertRaises(WebsiteError) as conflict:
            self.prepare()
        self.assertEqual(conflict.exception.code, "OFFER_CHANGED")
        self.assertEqual(CommercialOrderRequest.objects.count(), 1)

    def test_public_preparation_is_closed_even_for_verified_owner(self):
        response = self.owner.post(self.base, {"items": self.items, "offerFingerprint": self.fingerprint}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(self.key))
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.json()["code"], "COMMERCE_DISABLED")
        self.assertFalse(CommercialOrderRequest.objects.exists())

    def test_share_confirmation_and_current_notice_cannot_be_assumed(self):
        with self.assertRaises(WebsiteError):
            self.prepare(share_confirmed=False)
        CommercialConsent.objects.filter(user=self.person).delete()
        with self.assertRaises(WebsiteError) as error:
            self.prepare()
        self.assertEqual(error.exception.code, "CONSENT_REQUIRED")
        privacy = self.base.replace("order-requests/", "privacy/")
        self.assertFalse(self.owner.get(privacy).json()["accepted"])
        result = self.owner.post(privacy, {"noticeVersion": self.notice.version, "accepted": True}, content_type="application/json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.prepare().privacy_notice_id, self.notice.pk)

    def test_history_only_belongs_to_current_account_and_customer_and_cancellation_is_not_receipt(self):
        row = self.prepare()
        result = self.owner.get(self.base)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["count"], 1)
        self.assertIsNone(result.json()["results"][0]["whatsappUrl"])
        self.assertIn(self.authenticated(self.worker).get(self.base).status_code, (401, 403))
        detail = self.base + str(row.pk) + "/"
        invalid = self.owner.post(detail + "cancel/", {"status": "RECEIVED"}, content_type="application/json")
        self.assertEqual(invalid.status_code, 400)
        cancelled = self.owner.post(detail + "cancel/", {}, content_type="application/json")
        self.assertEqual(cancelled.json()["status"], "CANCELLED")
        self.assertEqual(self.owner.post(detail + "cancel/", {}, content_type="application/json").json()["status"], "CANCELLED")
        other = Customer.objects.create(company=self.a, document_type="0", legal_name="Other represented customer")
        CommercialAccount.objects.filter(pk=self.account.pk).update(customer=other)
        fresh = start_session(self.person, "a.catalog.test")
        client = Client(HTTP_AUTHORIZATION="Bearer " + fresh["access"])
        self.assertEqual(client.get(detail).status_code, 404)

    def test_expiration_is_effective_on_read_and_never_marks_received(self):
        row = self.prepare()
        CommercialOrderRequest.objects.filter(pk=row.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        row.refresh_from_db()
        self.assertEqual(services.request_data(row)["status"], "EXPIRED")
        self.assertIsNone(services.request_data(row, allow_whatsapp=True)["whatsappUrl"])
        with self.assertRaises(WebsiteError):
            self.prepare()
