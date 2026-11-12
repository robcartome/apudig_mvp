from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.companies.models import Company
from apps.websites.models import Website, WebsiteDomain, WebsiteSettings, normalize_hostname


class WebsiteDomainTest(TestCase):
    def setUp(self):
        company = Company.objects.create(name="Empresa", ruc="20999999999")
        self.website = Website.objects.create(company=company, name="Tienda")

    def test_hostname_is_normalized(self):
        domain = WebsiteDomain.objects.create(
            website=self.website,
            hostname="TIENDA.Example.COM.",
        )
        self.assertEqual(domain.hostname, "tienda.example.com")

    def test_website_gets_isolated_settings_and_slug(self):
        self.assertTrue(self.website.slug)
        settings = WebsiteSettings.objects.get(website=self.website)
        self.assertEqual(settings.business_name, "Tienda")
        self.assertEqual(self.website.template_key, "ecommerce")
        self.assertEqual(self.website.template_schema_version, 1)

    def test_unregistered_template_is_rejected(self):
        self.website.template_key = "corporate"
        with self.assertRaises(ValidationError):
            self.website.save()

    def test_reserved_apudig_hostname_is_rejected(self):
        with self.assertRaises(ValidationError):
            WebsiteDomain.objects.create(
                website=self.website,
                hostname="web.apudig.com",
            )

    def test_active_domain_requires_verification(self):
        with self.assertRaises(ValidationError):
            WebsiteDomain.objects.create(
                website=self.website,
                hostname="tienda.example.com",
                status=WebsiteDomain.Status.ACTIVE,
            )

    def test_verified_active_domain_is_valid(self):
        domain = WebsiteDomain.objects.create(
            website=self.website,
            hostname="tienda.example.com",
            status=WebsiteDomain.Status.ACTIVE,
            verified_at=timezone.now(),
        )
        self.assertEqual(domain.status, WebsiteDomain.Status.ACTIVE)

    def test_protocol_port_path_and_ip_are_rejected(self):
        for invalid in (
            "https://tienda.example.com",
            "tienda.example.com:443",
            "tienda.example.com/catalog",
            "127.0.0.1",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                normalize_hostname(invalid)
