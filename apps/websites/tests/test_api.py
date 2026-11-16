import datetime

from django.conf import settings
from django.test import TestCase
from django.urls import Resolver404, resolve

from apps.api.v1.auth.tokens import build_token
from apps.companies.models import Company, Store, UserCompanyAccess
from apps.users.models import Permission, Role, RolePermission, User, UserRole, UserStore
from apps.websites.models import Website
from apps.websites.permissions import WebsiteAccessDenied, website_capabilities
from apps.websites.selectors import get_company_website


class WebsiteDiscoveryTest(TestCase):
    url = "/api/v1/websites/current/"

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="A", ruc="20999999101")
        cls.other_company = Company.objects.create(name="B", ruc="20999999102")
        cls.website = Website.objects.create(company=cls.company, name="Web A")
        cls.other = Website.objects.create(company=cls.other_company, name="Web B")
        cls.user = User.objects.create_user(email="website-a@example.com")
        cls.access = UserCompanyAccess.objects.create(user=cls.user, company=cls.company)
        cls.role = Role.objects.create(name="Website reader")
        cls.user_role = UserRole.objects.create(user=cls.user, role=cls.role, company=cls.company)
        cls.permission = Permission.objects.get(code="read.website")
        RolePermission.objects.create(role=cls.role, permission=cls.permission)

    def token(self, **kwargs):
        payload = {"sub": str(self.user.pk), "email": self.user.email, "type": "access", "company_id": str(self.company.pk), "store_id": None}
        payload.update(kwargs)
        return build_token(payload, settings.JWT_ACCESS_TTL)

    def get(self, token=None, **headers):
        return self.client.get(self.url, HTTP_AUTHORIZATION=f"Bearer {token or self.token()}", **headers)

    def test_discovers_only_active_company_with_expected_dto(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"id", "companyId", "templateKey", "documentSchemaVersion", "revision", "capabilities"})
        self.assertEqual(response.json()["id"], str(self.website.pk))
        self.assertEqual(response.json()["companyId"], str(self.company.pk))
        self.assertEqual(response.json()["revision"], 0)
        self.assertEqual(response.json()["documentSchemaVersion"], 3)
        self.assertEqual(response.json()["capabilities"], {"view": True, "edit": False, "publish": False, "mediaUpload": False, "domains": False, "realPublication": True})
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_query_and_forwarded_headers_cannot_change_company(self):
        response = self.client.get(self.url, {"company_id": str(self.other_company.pk), "website_id": str(self.other.pk)}, HTTP_AUTHORIZATION=f"Bearer {self.token()}", HTTP_X_FORWARDED_HOST="b.example.com", HTTP_X_COMPANY_ID=str(self.other_company.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(self.website.pk))

    def test_cross_company_selector_is_not_found(self):
        with self.assertRaises(Website.DoesNotExist):
            get_company_website(user=self.user, company_id=self.company.pk, website_id=self.other.pk)

    def test_other_company_claim_does_not_grant_membership(self):
        response = self.get(self.token(company_id=str(self.other_company.pk), permissions=["read.website"], roles=["ADMIN"]))
        self.assertEqual(response.status_code, 403)

    def test_missing_company_fails_before_website_query(self):
        with self.assertNumQueries(0), self.assertRaises(WebsiteAccessDenied):
            get_company_website(user=self.user, company_id=None)
        response = self.get(self.token(company_id=None))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "COMPANY_REQUIRED")

    def test_session_cannot_supply_missing_token_scope(self):
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session.save()
        self.assertEqual(self.get(self.token(company_id=None)).status_code, 403)

    def test_anonymous_invalid_expired_refresh_and_inactive_user_rejected(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)
        invalid = "invalid.token"
        expired = build_token({"sub": str(self.user.pk), "type": "access"}, datetime.timedelta(seconds=-5))
        for token in (invalid, expired, self.token(type="refresh")):
            with self.subTest(token_kind=token[:7]):
                response = self.get(token)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response["WWW-Authenticate"], "Bearer")
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.get().status_code, 401)

    def test_malformed_company_claim_denied(self):
        self.assertEqual(self.get(self.token(company_id="not-a-uuid")).status_code, 403)

    def test_revoked_membership_denies_still_signed_token(self):
        token = self.token()
        self.access.delete()
        self.assertEqual(self.get(token).status_code, 403)

    def test_revoked_admin_membership_does_not_keep_stale_role_access(self):
        role = Role.objects.create(name="ADMIN")
        UserRole.objects.create(user=self.user, role=role, company=self.company)
        self.access.delete()
        self.assertEqual(self.get().status_code, 403)

    def test_permission_is_rechecked_not_taken_from_claims(self):
        token = self.token(permissions=["read.website"])
        RolePermission.objects.filter(role=self.role).delete()
        self.assertEqual(self.get(token).status_code, 403)

    def test_missing_module_grants_do_not_enable_legacy_bypass(self):
        Permission.objects.filter(code__in=["read.website", "manage.website", "publish.website", "manage.website.media", "manage.website.domains"]).delete()
        self.assertEqual(self.get().status_code, 403)

    def test_inactive_company_denied(self):
        Company.objects.filter(pk=self.company.pk).update(is_active=False)
        self.assertEqual(self.get().status_code, 403)

    def test_no_get_bootstrap(self):
        self.website.delete()
        response = self.get()
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Website.objects.filter(company=self.company).exists())

    def test_capabilities_keep_all_grants_independent(self):
        RolePermission.objects.filter(role=self.role).delete()
        pairs = [("manage.website", "edit"), ("publish.website", "publish"), ("manage.website.media", "mediaUpload"), ("manage.website.domains", "domains")]
        for code, key in pairs:
            permission = Permission.objects.get(code=code)
            RolePermission.objects.create(role=self.role, permission=permission)
            data = self.get().json()["capabilities"]
            self.assertTrue(data[key])
            self.assertTrue(data["view"])
            for other_code, other_key in pairs:
                if other_code != code:
                    self.assertFalse(data[other_key])
            self.assertTrue(data["realPublication"])
            RolePermission.objects.filter(role=self.role).delete()

    def test_current_company_admin_has_capabilities(self):
        role = Role.objects.create(name="ADMIN")
        UserRole.objects.create(user=self.user, role=role, company=self.company)
        capabilities = self.get().json()["capabilities"]
        self.assertTrue(all(capabilities[key] for key in ("view", "edit", "publish", "domains", "mediaUpload")))

    def test_superuser_still_requires_explicit_active_company(self):
        User.objects.filter(pk=self.user.pk).update(is_superuser=True)
        self.access.delete()
        self.assertEqual(self.get().status_code, 200)
        self.assertEqual(self.get(self.token(company_id=None)).status_code, 403)

    def test_store_context_requires_current_access_and_valid_relation(self):
        store = Store.objects.create(company=self.company, name="A branch")
        self.access.delete()
        UserCompanyAccess.objects.create(user=self.user, company=self.company, store=store)
        assignment = UserStore.objects.create(user=self.user, store=store, role="SELLER")
        token = self.token(store_id=str(store.pk))
        self.assertEqual(self.get(token).status_code, 200)
        assignment.is_active = False
        assignment.save()
        self.assertEqual(self.get(token).status_code, 403)

    def test_store_from_other_company_or_inactive_is_denied(self):
        other_store = Store.objects.create(company=self.other_company, name="B branch")
        inactive = Store.objects.create(company=self.company, name="Closed", active=False)
        for store in (other_store, inactive):
            self.assertEqual(self.get(self.token(store_id=str(store.pk))).status_code, 403)

    def test_selector_enforces_operation_permission(self):
        with self.assertRaises(WebsiteAccessDenied):
            get_company_website(user=self.user, company_id=self.company.pk, permission="publish")
        with self.assertRaises(WebsiteAccessDenied):
            website_capabilities(self.user, None)

    def test_discovery_is_read_only_and_commercial_routes_are_not_exposed(self):
        response = self.client.post(self.url, {}, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.token()}")
        self.assertEqual(response.status_code, 405)
        for suffix in (f"websites/{self.website.pk}/catalog-settings/", "storefront/resolve/", "storefront/sites/a.example.com/products/"):
            with self.subTest(path=suffix), self.assertRaises(Resolver404):
                resolve("/api/v1/" + suffix)
