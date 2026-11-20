"""Real PostgreSQL/domain/API tests; only the external SMTP connection is mocked."""
import hashlib
import io
import re
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.core.mail.backends.locmem import EmailBackend
from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.partners.models import Customer
from apps.users.models import User, UserRole, UserStore
from apps.companies.models import UserCompanyAccess
from apps.websites import registration as services
from apps.websites.errors import WebsiteError
from apps.websites.models import CommercialAccount, CommercialConsent, CommercialRegistration, WebsiteEmailOutbox, WebsitePrivacyNotice
from apps.websites.registration_mail import send_queued_emails, verification_url
from .test_catalog import CommercialCatalogFixture


@override_settings(WEBSITE_REGISTRATION_ENABLED=True, WEBSITE_EMAIL_BACKEND="smtp", WEBSITE_SMTP_HOST="smtp.integration.invalid", WEBSITE_EMAIL_FROM="noreply@integration.invalid", WEBSITE_SMTP_USER="synthetic", WEBSITE_SMTP_PASSWORD="synthetic", WEBSITE_SMTP_USE_TLS=True, WEBSITE_SMTP_USE_SSL=False)
class CommercialRegistrationTest(CommercialCatalogFixture, TestCase):
    password = "Synthetic-registered-password-2026!"

    def setUp(self):
        super().setUp()
        cache.clear()
        self.notice = self.configure()

    def configure(self, version="v1", mode="NEW_OR_REVIEW"):
        return services.configure_notice(user=self.admin, company_id=self.a.pk, website_id=self.site.pk, version=version, text="Synthetic fixture notice, not a production privacy notice.", pending_retention_days=3, linking_mode=mode, expected=services.policy_etag(services.policy_for(self.site)))

    def start(self, email="new-customer@integration.invalid", purpose="REGISTER", name="New client"):
        services.start_registration("a.catalog.test", email=email, name=name, notice_version=self.notice.version, consent=True, purpose=purpose)

    def deliver(self):
        with patch("apps.websites.registration_mail.get_connection", return_value=EmailBackend()):
            result = send_queued_emails()
        self.assertEqual(result["failed"], 0)
        return re.search(r"#token=([A-Za-z0-9_-]+)", mail.outbox[-1].body).group(1)

    def complete(self, secret, identity=None):
        return services.complete_registration("a.catalog.test", secret=secret, password=self.password, identity=identity)

    def api_url(self, suffix="registrations/"):
        return "/api/v1/storefront/sites/a.catalog.test/" + suffix

    def test_closed_registration_creates_no_user_registration_or_email(self):
        before = User.objects.count()
        with override_settings(WEBSITE_REGISTRATION_ENABLED=False):
            self.assertFalse(services.public_registration_policy("a.catalog.test")["registrationEnabled"])
            with self.assertRaises(WebsiteError) as error:
                self.start()
            self.assertEqual(error.exception.status, 503)
        self.assertEqual(User.objects.count(), before)
        self.assertFalse(CommercialRegistration.objects.exists())
        self.assertFalse(WebsiteEmailOutbox.objects.exists())

    def test_local_email_origin_never_overrides_production_or_another_host(self):
        with override_settings(DEBUG=True, WEBSITE_EMAIL_DEV_ORIGIN="http://demo.localhost:3000"):
            self.assertTrue(verification_url("demo.localhost", "verificar-cuenta", "secret").startswith("http://demo.localhost:3000/"))
            self.assertTrue(verification_url("other.localhost", "verificar-cuenta", "secret").startswith("https://other.localhost/"))
        with override_settings(DEBUG=False, WEBSITE_EMAIL_DEV_ORIGIN="http://demo.localhost:3000"):
            self.assertTrue(verification_url("demo.localhost", "verificar-cuenta", "secret").startswith("https://demo.localhost/"))

    def test_missing_provider_does_not_fake_delivery_or_persist_signup(self):
        with override_settings(WEBSITE_EMAIL_BACKEND="disabled"):
            with self.assertRaises(WebsiteError):
                self.start()
        self.assertFalse(CommercialRegistration.objects.exists())

    def test_request_only_queues_hash_not_secret_or_password_or_user(self):
        before = User.objects.count()
        self.start()
        row = CommercialRegistration.objects.get()
        self.assertIsNone(row.token_digest)
        self.assertEqual(User.objects.count(), before)
        secret = self.deliver()
        row.refresh_from_db()
        self.assertEqual(row.token_digest, hashlib.sha256(secret.encode()).hexdigest())
        self.assertNotIn(secret, str(row.__dict__))
        self.assertNotIn(self.password, str(row.__dict__))
        self.assertIn("https://a.catalog.test/verificar-cuenta#token=", mail.outbox[-1].body)

    def test_verified_new_customer_reuses_erp_service_without_employee_grants(self):
        self.start()
        result = self.complete(self.deliver())
        self.assertEqual(result["status"], "COMPLETE")
        user = User.objects.get(email="new-customer@integration.invalid")
        account = CommercialAccount.objects.get(user=user, company=self.a)
        self.assertTrue(user.check_password(self.password))
        self.assertEqual(account.customer.company_id, self.a.pk)
        self.assertIsNotNone(account.verified_at)
        self.assertIsNone(account.wholesale_approved_at)
        self.assertFalse(UserCompanyAccess.objects.filter(user=user).exists())
        self.assertFalse(UserRole.objects.filter(user=user).exists())
        self.assertFalse(UserStore.objects.filter(user=user).exists())
        self.assertEqual(CommercialConsent.objects.get(user=user).notice_id, self.notice.pk)

    def test_matching_customer_requires_review_without_appropriating_or_modifying_it(self):
        customer = Customer.objects.create(company=self.a, document_type="0", legal_name="Existing master", email="new-customer@integration.invalid", address="Keep fiscal data")
        self.start()
        self.assertEqual(self.complete(self.deliver())["status"], "REVIEW")
        self.assertFalse(CommercialAccount.objects.exists())
        customer.refresh_from_db()
        self.assertEqual(customer.address, "Keep fiscal data")
        registration = CommercialRegistration.objects.get()
        services.review_registration(user=self.admin, company_id=self.a.pk, website_id=self.site.pk, registration_id=registration.pk, customer_id=customer.pk)
        self.assertEqual(CommercialAccount.objects.get().customer_id, customer.pk)

    def test_existing_identity_requires_authentication_and_never_changes_credentials(self):
        self.start(email=self.worker.email)
        secret = self.deliver()
        previous = self.worker.password
        with self.assertRaises(WebsiteError) as error:
            self.complete(secret)
        self.assertEqual(error.exception.code, "IDENTITY_LOGIN_REQUIRED")
        with self.assertRaises(WebsiteError):
            self.complete(secret, identity=self.reader)
        self.complete(secret, identity=self.worker)
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.password, previous)

    def test_duplicate_case_insensitive_identities_are_not_guessed(self):
        User.objects.create_user(email=self.worker.email.upper())
        self.start(email=self.worker.email)
        with self.assertRaises(WebsiteError) as error:
            self.complete(self.deliver(), identity=self.worker)
        self.assertEqual(error.exception.code, "IDENTITY_REVIEW_REQUIRED")

    def test_purpose_tenant_expiry_and_single_use_are_enforced(self):
        self.start()
        secret = self.deliver()
        with self.assertRaises(WebsiteError):
            services.recover_password("a.catalog.test", secret=secret, password=self.password)
        with self.assertRaises(WebsiteError):
            services.complete_registration("b.catalog.test", secret=secret, password=self.password)
        row = CommercialRegistration.objects.get()
        row.expires_at = timezone.now() - timedelta(seconds=1)
        row.save()
        with self.assertRaises(WebsiteError):
            self.complete(secret)
        row.expires_at = timezone.now() + timedelta(minutes=1)
        row.save()
        self.complete(secret)
        with self.assertRaises(WebsiteError):
            self.complete(secret)

    def test_notice_is_immutable_consent_required_and_changes_require_new_acceptance(self):
        with self.assertRaises(WebsiteError):
            services.start_registration("a.catalog.test", email="new@integration.invalid", notice_version="old", consent=True)
        self.notice.text = "Changed"
        with self.assertRaises(ValidationError):
            self.notice.save()
        self.start()
        secret = self.deliver()
        self.configure(version="v2")
        with self.assertRaises(WebsiteError) as error:
            self.complete(secret)
        self.assertEqual(error.exception.code, "NOTICE_CHANGED")

    def test_password_validation_happens_before_identity_creation(self):
        self.start()
        secret = self.deliver()
        with self.assertRaises(WebsiteError):
            services.complete_registration("a.catalog.test", secret=secret, password="123")
        self.assertFalse(User.objects.filter(email="new-customer@integration.invalid").exists())

    def test_recovery_revokes_commercial_sessions_and_rejects_mixed_employee_identity(self):
        self.start()
        self.complete(self.deliver())
        user = User.objects.get(email="new-customer@integration.invalid")
        from apps.websites.commercial_sessions import start_session, resolve_session
        from apps.api.v1.auth.tokens import decode_token
        tokens = start_session(user, "a.catalog.test")
        CommercialRegistration.objects.all().delete()
        self.start(email=user.email, purpose="RECOVERY")
        secret = self.deliver()
        services.recover_password("a.catalog.test", secret=secret, password="Different-synthetic-password-2026!")
        with self.assertRaises(WebsiteError):
            resolve_session(decode_token(tokens["access"]), "a.catalog.test")
        CommercialRegistration.objects.all().delete()
        self.start(email=self.worker.email, purpose="RECOVERY")
        with self.assertRaises(WebsiteError) as error:
            services.recover_password("a.catalog.test", secret=self.deliver(), password=self.password)
        self.assertEqual(error.exception.code, "CENTRAL_RECOVERY_REQUIRED")

    def test_review_all_mode_and_cms_cannot_link_customer(self):
        self.configure(version="v2", mode="REVIEW_ALL")
        self.notice = services.policy_for(self.site).notice
        self.start()
        self.assertEqual(self.complete(self.deliver())["status"], "REVIEW")
        registration = CommercialRegistration.objects.get()
        foreign = Customer.objects.create(company=self.b, document_type="0", legal_name="Foreign")
        from apps.websites.permissions import WebsiteAccessDenied
        with self.assertRaises(WebsiteAccessDenied):
            services.review_registration(user=self.editor, company_id=self.a.pk, website_id=self.site.pk, registration_id=registration.pk, customer_id=foreign.pk)
        with self.assertRaises(WebsiteError):
            services.review_registration(user=self.admin, company_id=self.a.pk, website_id=self.site.pk, registration_id=registration.pk, customer_id=foreign.pk)

    def test_no_enumeration_in_start_response_and_recipient_cooldown(self):
        client = Client()
        common = {"name": "Name", "consent": True, "noticeVersion": "v1"}
        known = client.post(self.api_url(), {**common, "email": self.worker.email}, content_type="application/json")
        unknown = client.post(self.api_url(), {**common, "email": "unknown@integration.invalid"}, content_type="application/json")
        self.assertEqual(known.status_code, 202)
        self.assertEqual(known.json(), unknown.json())
        self.start(email=self.worker.email)
        self.assertEqual(CommercialRegistration.objects.filter(email=self.worker.email).count(), 1)

    def test_policy_administration_is_scoped_and_preconditioned(self):
        path = f"/api/v1/websites/{self.site.pk}/registration-policy/"
        data = {"version": "v2", "text": "Synthetic second notice", "pendingRetentionDays": 2, "linkingMode": "REVIEW_ALL"}
        etag = self.client.get(path)["ETag"]
        self.assertEqual(self.client.post(path, data, content_type="application/json").status_code, 428)
        saved = self.client.post(path, data, content_type="application/json", HTTP_IF_MATCH=etag)
        self.assertEqual(saved.status_code, 201, saved.content)
        self.assertEqual(self.client.post(path, {**data, "version": "v3"}, content_type="application/json", HTTP_IF_MATCH=etag).status_code, 412)
        self.assertEqual(self.authenticated(self.editor).get(path).status_code, 403)

    def test_smtp_failure_keeps_no_secret_or_raw_sensitive_error(self):
        self.start()
        with patch("apps.websites.registration_mail.deliver_email", side_effect=RuntimeError("secret-credentials-and-recipient")):
            self.assertEqual(send_queued_emails()["failed"], 1)
        job = WebsiteEmailOutbox.objects.get()
        self.assertEqual(job.error_code, "RuntimeError")
        self.assertNotIn("secret-credentials", str(job.__dict__))
        self.assertIsNone(CommercialRegistration.objects.get().verified_at)

    def test_retention_purge_is_dry_run_by_default_and_preserves_global_user(self):
        self.start()
        self.complete(self.deliver())
        CommercialRegistration.objects.update(created_at=timezone.now() - timedelta(days=5))
        output = io.StringIO()
        call_command("purge_website_registrations", website=self.site.pk, stdout=output)
        self.assertIn("deleted=0", output.getvalue())
        call_command("purge_website_registrations", website=self.site.pk, execute=True, stdout=io.StringIO())
        self.assertFalse(CommercialRegistration.objects.exists())
        self.assertTrue(User.objects.filter(email="new-customer@integration.invalid").exists())
