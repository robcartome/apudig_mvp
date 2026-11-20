from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core.mail.backends.locmem import EmailBackend
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.websites.registration import configure_notice, policy_etag, start_registration
from apps.websites.registration_mail import provider_ready, send_queued_emails
from apps.websites.models import WebsiteEmailOutbox
from .test_catalog import CommercialCatalogFixture


@override_settings(WEBSITE_REGISTRATION_ENABLED=True, WEBSITE_EMAIL_BACKEND="smtp", WEBSITE_SMTP_HOST="smtp.integration.invalid", WEBSITE_EMAIL_FROM="noreply@integration.invalid", WEBSITE_SMTP_USER="synthetic", WEBSITE_SMTP_PASSWORD="synthetic", WEBSITE_SMTP_PORT=587, WEBSITE_SMTP_USE_TLS=True, WEBSITE_SMTP_USE_SSL=False)
class RegistrationDeliveryTest(CommercialCatalogFixture, TestCase):
    def setUp(self):
        super().setUp()
        configure_notice(user=self.admin, company_id=self.a.pk, website_id=self.site.pk, version="synthetic-v1", text="Synthetic delivery test notice only", pending_retention_days=3, linking_mode="NEW_OR_REVIEW", expected=policy_etag(None))
        start_registration("a.catalog.test", email="synthetic@integration.invalid", name="Synthetic", notice_version="synthetic-v1", consent=True)

    def test_successful_queue_is_not_delivered_twice_and_immediate_retries_wait(self):
        with patch("apps.websites.registration_mail.get_connection", return_value=EmailBackend()):
            self.assertEqual(send_queued_emails(), {"sent": 1, "failed": 0})
            self.assertEqual(send_queued_emails(), {"sent": 0, "failed": 0})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(WebsiteEmailOutbox.objects.get().attempts, 1)

    def test_stale_claim_is_recovered_but_attempts_are_bounded(self):
        job = WebsiteEmailOutbox.objects.get()
        job.status, job.attempts = "SENDING", 1
        job.last_attempt_at = timezone.now() - timedelta(minutes=16)
        job.save()
        with patch("apps.websites.registration_mail.get_connection", return_value=EmailBackend()):
            self.assertEqual(send_queued_emails()["sent"], 1)
            job.refresh_from_db()
            self.assertEqual(job.attempts, 2)
            job.status, job.attempts = "FAILED", 3
            job.last_attempt_at = timezone.now() - timedelta(minutes=16)
            job.save()
            self.assertEqual(send_queued_emails(), {"sent": 0, "failed": 0})

    def test_invalid_provider_never_becomes_real_verification(self):
        for values in ({"WEBSITE_SMTP_USE_SSL": True}, {"WEBSITE_SMTP_PORT": 0}, {"WEBSITE_EMAIL_FROM": "bad"}, {"WEBSITE_EMAIL_BACKEND": "locmem"}, {"WEBSITE_SMTP_HOST": "bad\r\nhost"}):
            with override_settings(**values):
                self.assertFalse(provider_ready())
