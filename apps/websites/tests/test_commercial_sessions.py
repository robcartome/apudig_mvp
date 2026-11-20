from datetime import timedelta
from django.conf import settings
from django.test import Client, TestCase
from django.utils import timezone

from apps.api.v1.auth.tokens import build_token, decode_token, build_access_from_refresh_payload
from apps.companies.models import UserCompanyAccess
from apps.partners.models import Customer, SalesCustomerProfile
from apps.users.models import User, UserRole, UserStore
from apps.websites.accounts import issue_email_challenge, verify_email_challenge
from apps.websites.models import CommercialAccount, CommercialSession, WebsiteDomain
from .test_catalog import CommercialCatalogFixture


class CommercialSessionTest(CommercialCatalogFixture, TestCase):
    password = "Synthetic-commercial-strong-password-2026!"

    def setUp(self):
        super().setUp()
        self.person = User.objects.create_user(email="customer@session.example.test", password=self.password, name="Cliente sintético", phone="999111222")
        self.customer = Customer.objects.create(company=self.a, document_type="0", legal_name="Customer A", address="PRIVATE FISCAL", email="private-erp@example.test")
        self.customer_b = Customer.objects.create(company=self.b, document_type="0", legal_name="Customer B")
        self.account = self.make_account(self.person, self.site, self.customer)
        self.public = Client()

    def make_account(self, user, website, customer):
        account = CommercialAccount.objects.create(company=website.company, user=user, customer=customer)
        secret = issue_email_challenge(user, website)
        verify_email_challenge(user, website, secret)
        account.refresh_from_db()
        return account

    def login(self, host="a.catalog.test", user=None):
        user = user or self.person
        return self.public.post("/api/v1/auth/token/", {"email": user.email, "password": self.password, "context": "commercial", "hostname": host}, content_type="application/json")

    def client_for(self, response=None):
        response = response or self.login()
        self.assertEqual(response.status_code, 200, response.content)
        return Client(HTTP_AUTHORIZATION="Bearer " + response.json()["access"])

    def profile_url(self, host="a.catalog.test"):
        return f"/api/v1/storefront/sites/{host}/account/"

    def admin_accounts(self, account=None):
        suffix = f"{account.pk}/" if account else ""
        return f"/api/v1/websites/{self.site.pk}/commercial-accounts/{suffix}"

    def test_customer_without_labor_membership_logs_in_and_reads_own_profile(self):
        response = self.login()
        client = self.client_for(response)
        data = client.get(self.profile_url()).json()
        self.assertEqual(data["user"]["name"], "Cliente sintético")
        self.assertTrue(data["contactVerified"])
        self.assertFalse(data["capabilities"]["prepareOrders"])
        self.assertNotIn("company_id", decode_token(response.json()["access"]))
        self.assertFalse(UserCompanyAccess.objects.filter(user=self.person).exists())
        self.assertFalse(UserRole.objects.filter(user=self.person).exists())
        self.assertFalse(UserStore.objects.filter(user=self.person).exists())
        self.assertIn("no-store", client.get(self.profile_url())["Cache-Control"])

    def test_profile_has_no_customer_fiscal_private_or_labor_fields(self):
        client = self.client_for()
        response = client.get(self.profile_url())
        text = response.content.decode()
        for forbidden in ("PRIVATE FISCAL", "private-erp", "customerId", "roles", "permissions", "priceList", "warehouse", "supplier", "is_superuser"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(client.get(self.profile_url(), {"customer_id": self.customer_b.pk}).status_code, 400)
        self.assertEqual(client.patch(self.profile_url(), {"email": "takeover@example.test"}, content_type="application/json").status_code, 405)

    def test_explicit_exchange_accepts_existing_identity_without_company(self):
        token = build_token({"sub": str(self.person.pk), "type": "access"}, settings.JWT_ACCESS_TTL)
        client = Client(HTTP_AUTHORIZATION="Bearer " + token)
        response = client.post(self.profile_url() + "session/", {}, content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["context"], "commercial")
        self.assertEqual(client.get(self.profile_url()).status_code, 401)

    def test_commercial_user_of_two_companies_switches_explicitly_with_new_tokens(self):
        self.make_account(self.person, self.foreign_site, self.customer_b)
        a = self.client_for()
        self.assertEqual(a.get(self.profile_url("b.catalog.test")).status_code, 401)
        switched = a.post(self.profile_url("b.catalog.test") + "session/", {}, content_type="application/json")
        b = self.client_for(switched)
        self.assertEqual(b.get(self.profile_url("b.catalog.test")).json()["company"]["name"], self.b.name)
        self.assertEqual(b.get(self.profile_url()).status_code, 401)
        self.assertEqual(a.get(self.profile_url()).status_code, 200)

    def test_user_of_a_cannot_enter_b_or_choose_customer_in_body(self):
        client = self.client_for()
        self.assertEqual(client.post(self.profile_url("b.catalog.test") + "session/", {}, content_type="application/json").status_code, 403)
        self.assertEqual(client.post(self.profile_url() + "session/", {"customer_id": str(self.customer_b.pk)}, content_type="application/json").status_code, 400)

    def test_commercial_access_never_authorizes_erp_cms_or_context_selection(self):
        client = self.client_for()
        for url in ("/api/v1/auth/me/", "/api/v1/auth/my-companies/", "/api/v1/catalog/products/", "/api/v1/products/", "/api/v1/websites/current/", self.admin_accounts()):
            with self.subTest(url=url):
                self.assertIn(client.get(url).status_code, (401, 403))
        self.assertIn(client.post("/api/v1/auth/select-company/", {"company_id": str(self.a.pk)}, content_type="application/json").status_code, (401, 403))

    def test_worker_customer_and_labor_login_remain_independent(self):
        self.worker.set_password(self.password)
        self.worker.save()
        self.make_account(self.worker, self.site, self.customer)
        commercial = self.client_for(self.login(user=self.worker))
        self.assertIn(commercial.get("/api/v1/catalog/products/").status_code, (401, 403))
        labor = self.authenticated(self.worker)
        self.assertEqual(labor.get("/api/v1/catalog/products/").status_code, 200)
        self.assertEqual(labor.get(self.profile_url()).status_code, 401)
        legacy = self.public.post("/api/v1/auth/token/", {"email": self.worker.email, "password": self.password}, content_type="application/json")
        self.assertEqual(legacy.status_code, 200)
        self.assertIn("companies", legacy.json())

    def test_refresh_preserves_purpose_domain_and_current_approval(self):
        login = self.login().json()
        data = {"refresh_token": login["refresh"], "hostname": "a.catalog.test"}
        response = self.public.post("/api/v1/auth/refresh/", data, content_type="application/json")
        client = self.client_for(response)
        self.assertEqual(decode_token(response.json()["access"])["purpose"], "commercial")
        self.assertEqual(client.get(self.profile_url()).status_code, 200)
        data["hostname"] = "b.catalog.test"
        self.assertEqual(self.public.post("/api/v1/auth/refresh/", data, content_type="application/json").status_code, 401)
        with self.assertRaises(ValueError):
            build_access_from_refresh_payload(decode_token(login["refresh"]))

    def test_logout_revokes_both_access_and_refresh_but_is_idempotent(self):
        response = self.login()
        client = self.client_for(response)
        data = {"refresh_token": response.json()["refresh"]}
        for _ in range(2):
            self.assertEqual(self.public.post("/api/v1/auth/logout/", data, content_type="application/json").status_code, 204)
        self.assertEqual(client.get(self.profile_url()).status_code, 401)
        data["hostname"] = "a.catalog.test"
        self.assertEqual(self.public.post("/api/v1/auth/refresh/", data, content_type="application/json").status_code, 401)

    def test_expired_jwt_and_session_are_rejected(self):
        response = self.login()
        claims = decode_token(response.json()["access"])
        expired = build_token({k: v for k, v in claims.items() if k not in ("iat", "exp")}, timedelta(seconds=-1))
        self.assertEqual(Client(HTTP_AUTHORIZATION="Bearer " + expired).get(self.profile_url()).status_code, 401)
        CommercialSession.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client_for(response).get(self.profile_url()).status_code, 401)

    def test_contact_status_and_customer_changes_are_revalidated_without_new_jwt(self):
        for field, value in (("status", "SUSPENDED"), ("status", "REVOKED"), ("verified_at", None)):
            response = self.login()
            with self.subTest(field=field, value=value):
                CommercialAccount.objects.filter(pk=self.account.pk).update(**{field: value})
                self.assertIn(self.client_for(response).get(self.profile_url()).status_code, (401, 403))
                self.assertEqual(self.login().status_code, 403)
                CommercialAccount.objects.filter(pk=self.account.pk).update(status="ACTIVE", verified_at=self.account.verified_at)
        client = self.client_for()
        self.customer.active = False
        self.customer.save()
        self.assertIn(client.get(self.profile_url()).status_code, (401, 403))

    def test_domain_or_company_deactivation_prevents_protected_access(self):
        client = self.client_for()
        WebsiteDomain.objects.filter(website=self.site).update(status="PENDING", verified_at=None)
        self.assertIn(client.get(self.profile_url()).status_code, (401, 403, 404))

    def test_administrator_sees_only_own_accounts_and_can_revoke_wholesale(self):
        self.make_account(self.person, self.foreign_site, self.customer_b)
        SalesCustomerProfile.objects.create(customer=self.customer, price_list=self.price_list)
        page = self.client.get(self.admin_accounts())
        self.assertEqual(page.status_code, 200, page.content)
        self.assertEqual(page.json()["count"], 1)
        row = page.json()["results"][0]
        self.assertEqual(row["priceList"]["id"], str(self.price_list.pk))
        customer_client = self.client_for()
        url = self.admin_accounts(self.account)
        missing = self.client.patch(url, {"wholesaleApproved": True}, content_type="application/json")
        self.assertEqual(missing.status_code, 428)
        result = self.client.patch(url, {"wholesaleApproved": True}, content_type="application/json", HTTP_IF_MATCH=row["etag"])
        self.assertEqual(result.status_code, 200, result.content)
        self.assertTrue(customer_client.get(self.profile_url()).json()["wholesaleApproved"])
        stale = self.client.patch(url, {"wholesaleApproved": False}, content_type="application/json", HTTP_IF_MATCH=row["etag"])
        self.assertEqual(stale.status_code, 412)
        result = self.client.patch(url, {"wholesaleApproved": False}, content_type="application/json", HTTP_IF_MATCH=result["ETag"])
        self.assertEqual(result.status_code, 200)
        self.assertFalse(customer_client.get(self.profile_url()).json()["wholesaleApproved"])

    def test_cms_editor_worker_and_foreign_context_cannot_manage_accounts(self):
        for user in (self.editor, self.worker, self.reader):
            with self.subTest(user=user.email):
                self.assertEqual(self.authenticated(user).get(self.admin_accounts()).status_code, 403)
        foreign = CommercialAccount.objects.create(user=self.reader, company=self.b, customer=self.customer_b)
        self.assertEqual(self.client.get(self.admin_accounts(foreign)).status_code, 404)

    def test_bearer_auth_does_not_accept_session_cookies_as_commercial_identity(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.person)
        self.assertEqual(browser.get(self.profile_url()).status_code, 401)
        self.assertEqual(browser.post(self.profile_url() + "session/", {}, content_type="application/json").status_code, 401)
