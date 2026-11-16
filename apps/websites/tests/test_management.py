from django.contrib import admin
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AuditLog
from apps.users.models import Permission, RolePermission, User, UserRole
from apps.websites import domain_services
from apps.websites.models import Website, WebsiteDomain, WebsitePageRevision
from .test_editorial import EditorialTestCase


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class WebsiteManagementTest(EditorialTestCase):
    def setUp(self):
        super().setUp()
        RolePermission.objects.create(role=self.role, permission=Permission.objects.get(code="manage.website.domains"))
        self.client.force_login(self.user)
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session.save()
        self.management_url = reverse("websites:management")

    def domain(self, website=None, hostname="a.management.test"):
        return WebsiteDomain.objects.create(website=website or self.website, hostname=hostname)

    def post(self, operation, domain=None, **data):
        return self.client.post(self.management_url, {"operation": operation, **({"domain_id": str(domain.pk)} if domain else {}), **data})

    def test_get_shows_only_selected_company_and_never_creates(self):
        self.domain(self.other, "foreign.management.test")
        response = self.client.get(self.management_url)
        self.assertContains(response, "Web A")
        self.assertNotContains(response, "foreign.management.test")
        self.assertEqual(Website.objects.count(), 2)
        self.assertFalse(WebsitePageRevision.objects.exists())

    def test_create_is_explicit_idempotent_and_draft(self):
        self.website.delete()
        self.assertEqual(self.client.get(self.management_url).status_code, 200)
        self.assertFalse(Website.objects.filter(company=self.company).exists())
        self.assertEqual(self.post("create").status_code, 302)
        self.assertEqual(self.post("create").status_code, 302)
        website = Website.objects.get(company=self.company)
        self.assertEqual(website.status, "DRAFT")
        self.assertIsNone(website.published_revision_id)
        self.assertEqual(AuditLog.objects.filter(action="WEBSITE_CREATE").count(), 1)

    def test_register_normalizes_and_ignores_forged_activation_fields(self):
        response = self.post("register", hostname="A.Management.Test.", kind="CUSTOM", status="ACTIVE", verified_at="2026-11-16")
        self.assertEqual(response.status_code, 302)
        domain = WebsiteDomain.objects.get(website=self.website)
        self.assertEqual(domain.hostname, "a.management.test")
        self.assertEqual(domain.status, "PENDING")
        self.assertIsNone(domain.verified_at)
        self.assertFalse(domain.is_primary)

    def test_pending_domain_cannot_be_activated_or_primary(self):
        domain = self.domain()
        self.post("activate", domain)
        self.post("primary", domain)
        domain.refresh_from_db()
        self.assertEqual(domain.status, "PENDING")
        self.assertFalse(domain.is_primary)

    def test_domain_attestation_requires_platform_superuser_and_evidence(self):
        domain = self.domain()
        self.assertEqual(self.post("verify", domain, evidence="Explicit authorized local hostname provisioned for this company").status_code, 403)
        self.user.is_superuser = True
        self.user.save()
        self.post("verify", domain, evidence="too short")
        domain.refresh_from_db()
        self.assertEqual(domain.status, "PENDING")
        self.post("verify", domain, evidence="Explicit authorized local hostname provisioned for this company")
        domain.refresh_from_db()
        self.assertEqual(domain.status, "VERIFIED")
        self.assertIsNotNone(domain.verified_at)
        self.assertEqual(AuditLog.objects.filter(action="WEBSITE_DOMAIN_VERIFY").count(), 1)
        self.post("activate", domain)
        self.post("primary", domain)
        domain.refresh_from_db()
        self.assertEqual(domain.status, "ACTIVE")
        self.assertTrue(domain.is_primary)
        self.website.refresh_from_db()
        self.assertEqual(self.website.status, "DRAFT")
        self.post("disable", domain)
        domain.refresh_from_db()
        self.assertEqual(domain.status, "DISABLED")
        self.assertFalse(domain.is_primary)
        self.assertIsNone(domain.verified_at)

    def test_foreign_domain_and_missing_permission_are_denied(self):
        foreign = self.domain(self.other, "foreign.management.test")
        self.assertEqual(self.post("disable", foreign).status_code, 404)
        RolePermission.objects.filter(role=self.role, permission__code="manage.website.domains").delete()
        self.assertEqual(self.post("register", hostname="new.management.test", kind="CUSTOM").status_code, 403)
        self.assertFalse(WebsiteDomain.objects.filter(website=self.website).exists())

    def test_revoked_membership_and_no_website_grants_cannot_read(self):
        RolePermission.objects.filter(role=self.role).delete()
        self.assertEqual(self.client.get(self.management_url).status_code, 403)

    def test_writes_require_csrf_and_anonymous_requests_require_login(self):
        anonymous = Client()
        self.assertEqual(anonymous.get(self.management_url).status_code, 302)
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.user)
        self.assertEqual(protected.post(self.management_url, {"operation": "create"}).status_code, 403)

    def test_django_admin_is_inspection_only_for_platform_superusers(self):
        request = RequestFactory().get("/admin/")
        request.user = self.user
        for model in (Website, WebsiteDomain, WebsitePageRevision):
            registration = admin.site._registry[model]
            self.assertFalse(registration.has_view_permission(request))
            self.user.is_superuser = True
            self.assertTrue(registration.has_view_permission(request))
            self.assertFalse(registration.has_add_permission(request))
            self.assertFalse(registration.has_change_permission(request))
            self.assertFalse(registration.has_delete_permission(request))
            self.user.is_superuser = False

        self.user.is_superuser = True
        self.user.is_staff = True
        self.user.save()
        self.assertContains(self.client.get(reverse("admin:websites_website_changelist")), reverse("websites:management"))

    def test_primary_domain_switch_keeps_one_primary(self):
        first = self.domain(hostname="first.management.test")
        second = self.domain(hostname="second.management.test")
        for domain in (first, second):
            domain.status = "ACTIVE"
            domain.verified_at = timezone.now()
            domain.save()
            self.assertEqual(self.post("primary", domain).status_code, 302)
        self.assertEqual(WebsiteDomain.objects.filter(website=self.website, is_primary=True).count(), 1)
        second.refresh_from_db()
        self.assertTrue(second.is_primary)

    def test_existing_user_management_assigns_website_permissions_through_roles(self):
        UserRole.objects.filter(user=self.user, company=self.company).delete()
        operator = User.objects.create_user(email="website-platform@example.test", is_superuser=True, is_staff=True)
        client = Client()
        client.force_login(operator)
        session = client.session
        session["active_company_id"] = str(self.company.pk)
        session.save()
        url = reverse("users:user_detail", kwargs={"pk": self.user.pk})
        self.assertContains(client.get(url + "?tab=roles"), "manage.website.domains")
        self.assertEqual(client.post(url, {"save_roles": "1", "role_ids": [str(self.role.pk)]}).status_code, 302)
        self.assertEqual(self.client.get(self.management_url).status_code, 200)
