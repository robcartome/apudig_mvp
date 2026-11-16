from dataclasses import asdict

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.companies.models import Company
from apps.websites.models import (
    Website, WebsiteDomain, WebsitePage, WebsitePageRevision,
    WebsiteSettings, normalize_hostname,
)
from apps.websites.selectors import resolve_public_website


class HostnameTest(SimpleTestCase):
    def test_normalizes_case_root_dot_and_idna(self):
        self.assertEqual(normalize_hostname("TIENDA.Example.COM."), "tienda.example.com")
        self.assertEqual(normalize_hostname("mañana.example.com"), "xn--maana-pta.example.com")

    def test_rejects_ambiguous_or_malformed_hosts(self):
        invalid = [
            None, 123, "", " ", " tienda.example", "tienda.example ",
            "tienda.example\n", "tienda\x00.example", "tien\u200bda.example",
            "https://tienda.example", "tienda.example:443", "tienda.example/path",
            "//tienda.example", "tienda\\example.com", "user@tienda.example",
            "127.0.0.1", "127.0.0.1.", "::1", "[::1]", "123.456",
            "0x7f.0.0.1", "127.0.0.0x1",
            "localhost", "-tienda.example", "tienda-.example", "a..example",
            "tienda.example..", "*.example", "a_b.example", "xn--a.example",
            "a" * 64 + ".example", ".".join(["a" * 63] * 4),
        ]
        for value in invalid:
            with self.subTest(value=repr(value)), self.assertRaises(ValidationError):
                normalize_hostname(value)


class WebsiteDomainTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Empresa A", ruc="20999999001", phone="original")
        cls.other_company = Company.objects.create(name="Empresa B", ruc="20999999002")
        cls.website = Website.objects.create(company=cls.company, name="Web A")
        cls.other = Website.objects.create(company=cls.other_company, name="Web B")

    def domain(self, **kwargs):
        values = {"website": self.website, "hostname": "a.example.com"}
        values.update(kwargs)
        return WebsiteDomain.objects.create(**values)

    def test_creation_is_draft_and_has_no_cms_bootstrap_or_publication(self):
        self.assertEqual(self.website.status, Website.Status.DRAFT)
        self.assertEqual(self.website.template_key, "ecommerce")
        self.assertEqual(self.website.editorial_revision, 0)
        self.assertIsNone(self.website.published_revision_id)
        self.assertIsNone(self.website.published_at)
        self.assertFalse(WebsiteSettings.objects.exists())
        self.assertFalse(WebsitePage.objects.exists())
        self.website.name = "Nuevo nombre web"
        self.website.save()
        self.company.refresh_from_db()
        self.assertEqual((self.company.name, self.company.phone), ("Empresa A", "original"))

    def test_one_website_per_company(self):
        with self.assertRaises(ValidationError):
            Website.objects.create(company=self.company, name="Duplicado")

    def test_unregistered_template_rejected(self):
        self.website.template_key = "corporate"
        with self.assertRaises(ValidationError):
            self.website.save()

    def test_normalized_domain_is_globally_unique(self):
        self.domain(hostname="A.EXAMPLE.COM.")
        with self.assertRaises(ValidationError):
            self.domain(website=self.other)

    def test_reserved_domains_rejected(self):
        for hostname in ("apudig.com", "api.apudig.com", "web.apudig.com"):
            with self.subTest(hostname=hostname), self.assertRaises(ValidationError):
                self.domain(hostname=hostname)

    def test_domain_defaults_pending_without_verification(self):
        domain = self.domain()
        self.assertEqual(domain.status, "PENDING")
        self.assertIsNone(domain.verified_at)
        self.assertFalse(domain.is_primary)
        with self.assertRaises(Website.DoesNotExist):
            resolve_public_website(domain.hostname)

    def test_verification_and_primary_invariants_validated(self):
        for values in (
            {"status": "ACTIVE"}, {"status": "VERIFIED"},
            {"status": "PENDING", "verified_at": timezone.now()},
            {"status": "PENDING", "is_primary": True},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.domain(**values)

    def test_constraints_protect_bulk_writes(self):
        for values in (
            {"status": "ACTIVE"}, {"status": "VERIFIED"},
            {"status": "PENDING", "verified_at": timezone.now()},
            {"status": "DISABLED", "is_primary": True},
            {"hostname": "UPPER.example.com"}, {"hostname": "a.example.com."},
            {"hostname": "127.0.0.1"}, {"status": "UNKNOWN"},
        ):
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                defaults = {"website": self.website, "hostname": "a.example.com"}
                defaults.update(values)
                WebsiteDomain.objects.bulk_create([WebsiteDomain(**defaults)])

    def test_only_one_primary_domain(self):
        self.domain(status="ACTIVE", verified_at=timezone.now(), is_primary=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            WebsiteDomain.objects.bulk_create([WebsiteDomain(
                website=self.website, hostname="second.example.com", status="ACTIVE",
                verified_at=timezone.now(), is_primary=True,
            )])

    def publish_fixture(self):
        # Explicit test fixture only; B1 has no publishing or DNS verification service.
        page = WebsitePage.objects.create(website=self.website, slug="home", title="Inicio", page_type="HOME", status="PUBLISHED", published_version=1)
        revision = WebsitePageRevision.objects.create(page=page, version=1, snapshot={"privateDraftSentinel": "never returned"})
        self.website.status = "PUBLISHED"
        self.website.published_at = timezone.now()
        self.website.published_revision = revision
        self.website.save()
        self.domain(status="ACTIVE", verified_at=timezone.now())
        return page, revision

    def test_unknown_host_never_resolves_first_company(self):
        self.publish_fixture()
        for host in ("unknown.example.com", "https://a.example.com", None):
            with self.subTest(host=host), self.assertRaises(Website.DoesNotExist):
                resolve_public_website(host)

    def test_public_resolution_returns_only_metadata_not_draft(self):
        self.publish_fixture()
        result = asdict(resolve_public_website("A.EXAMPLE.COM."))
        self.assertEqual(result["website_id"], self.website.id)
        self.assertEqual(set(result), {"website_id", "hostname", "template_key", "published_revision_id"})

    def test_public_resolution_rejects_inactive_domain(self):
        self.publish_fixture()
        for status in ("DISABLED", "VERIFIED", "PENDING"):
            WebsiteDomain.objects.update(status=status, verified_at=None if status == "PENDING" else timezone.now())
            with self.subTest(status=status), self.assertRaises(Website.DoesNotExist):
                resolve_public_website("a.example.com")

    def test_public_resolution_requires_active_company(self):
        self.publish_fixture()
        Company.objects.filter(pk=self.company.pk).update(is_active=False)
        with self.assertRaises(Website.DoesNotExist):
            resolve_public_website("a.example.com")

    def test_public_resolution_rejects_draft_or_suspended_website(self):
        self.publish_fixture()
        for status in ("DRAFT", "SUSPENDED"):
            Website.objects.filter(pk=self.website.pk).update(status=status)
            with self.subTest(status=status), self.assertRaises(Website.DoesNotExist):
                resolve_public_website("a.example.com")

    def test_published_flag_without_revision_cannot_resolve(self):
        self.domain(status="ACTIVE", verified_at=timezone.now())
        Website.objects.filter(pk=self.website.pk).update(status="PUBLISHED", published_at=timezone.now())
        with self.assertRaises(Website.DoesNotExist):
            resolve_public_website("a.example.com")

    def test_public_resolution_rejects_draft_page_pointer(self):
        page, _ = self.publish_fixture()
        WebsitePage.objects.filter(pk=page.pk).update(status="DRAFT")
        with self.assertRaises(Website.DoesNotExist):
            resolve_public_website("a.example.com")
        WebsitePage.objects.filter(pk=page.pk).update(status="PUBLISHED", published_version=2)
        with self.assertRaises(Website.DoesNotExist):
            resolve_public_website("a.example.com")

    def test_revision_cannot_belong_to_another_company(self):
        _, revision = self.publish_fixture()
        self.other.published_revision = revision
        with self.assertRaises(ValidationError):
            self.other.save()
        Website.objects.filter(pk=self.other.pk).update(published_revision=revision, status="PUBLISHED", published_at=timezone.now())
        self.domain(website=self.other, hostname="b.example.com", status="ACTIVE", verified_at=timezone.now())
        with self.assertRaises(Website.DoesNotExist):
            resolve_public_website("b.example.com")
