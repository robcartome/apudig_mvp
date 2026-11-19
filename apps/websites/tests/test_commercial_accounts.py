from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.companies.models import UserCompanyAccess
from apps.partners.models import Customer, SalesCustomerProfile
from apps.inventory.models import PriceList, ProductPrice
from apps.websites import accounts
from apps.websites.errors import WebsiteError
from apps.websites.models import CommercialAccount, CommercialEmailChallenge
from apps.websites.permissions import WebsiteAccessDenied
from .test_catalog import CommercialCatalogFixture


class CommercialAccountTest(CommercialCatalogFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.customer = Customer.objects.create(company=self.a, document_type="0", legal_name="Commercial client")
        self.customer_b = Customer.objects.create(company=self.b, document_type="0", legal_name="Commercial client B")
        self.account = CommercialAccount.objects.create(user=self.worker, company=self.a, customer=self.customer)

    def verify(self):
        secret = accounts.issue_email_challenge(self.worker, self.site)
        return accounts.verify_email_challenge(self.worker, self.site, secret)

    def approve(self, user=None, approved=True, company=None):
        return accounts.set_wholesale_approval(user=user or self.admin, company_id=(company or self.a).pk, account_id=self.account.pk, approved=approved)

    def test_verified_contact_allows_basic_account_without_wholesale_approval(self):
        with self.assertRaises(WebsiteError):
            accounts.resolve_commercial_account(self.worker, "a.catalog.test")

        self.verify()
        site, account = accounts.resolve_commercial_account(self.worker, "a.catalog.test")
        self.assertEqual(site.pk, self.site.pk)
        self.assertIsNone(accounts.customer_price_list(account))
        self.assertIsNone(account.wholesale_approved_at)

    def test_token_is_hashed_expiring_single_use_and_bound_to_user_tenant_email(self):
        secret = accounts.issue_email_challenge(self.worker, self.site)
        challenge = CommercialEmailChallenge.objects.get(account=self.account)
        self.assertNotEqual(challenge.token_digest, secret)
        with self.assertRaises(WebsiteError):
            accounts.verify_email_challenge(self.reader, self.site, secret)
        with self.assertRaises(WebsiteError):
            accounts.verify_email_challenge(self.worker, self.foreign_site, secret)
        accounts.verify_email_challenge(self.worker, self.site, secret)
        with self.assertRaises(WebsiteError):
            accounts.verify_email_challenge(self.worker, self.site, secret)

    def test_expired_or_changed_email_proof_is_not_valid(self):
        secret = accounts.issue_email_challenge(self.worker, self.site)
        CommercialEmailChallenge.objects.filter(account=self.account).update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(WebsiteError):
            accounts.verify_email_challenge(self.worker, self.site, secret)
        CommercialEmailChallenge.objects.filter(account=self.account).delete()
        self.verify()
        self.worker.email = "changed@example.test"
        self.worker.save()
        with self.assertRaises(WebsiteError):
            accounts.resolve_commercial_account(self.worker, "a.catalog.test")
        self.worker.email = "worker@catalog.example.test"
        self.worker.save()
        with self.assertRaises(WebsiteError):
            accounts.resolve_commercial_account(self.worker, "a.catalog.test")

    def test_issue_has_cooldown_and_does_not_mark_contact_verified(self):
        accounts.issue_email_challenge(self.worker, self.site)
        with self.assertRaises(WebsiteError) as error:
            accounts.issue_email_challenge(self.worker, self.site)
        self.assertEqual(error.exception.status, 429)
        self.account.refresh_from_db()
        self.assertIsNone(self.account.verified_at)

    def test_no_employee_membership_is_created_or_required_for_commercial_access(self):
        UserCompanyAccess.objects.filter(user=self.worker).delete()
        self.verify()
        accounts.resolve_commercial_account(self.worker, "a.catalog.test")
        self.assertFalse(UserCompanyAccess.objects.filter(user=self.worker).exists())
        self.assertEqual(self.authenticated(self.worker).get("/api/v1/catalog/products/").status_code, 403)

    def test_foreign_customer_link_and_duplicate_account_are_rejected(self):
        with self.assertRaises(ValidationError):
            CommercialAccount.objects.create(user=self.reader, company=self.a, customer=self.customer_b)
        with self.assertRaises(ValidationError):
            CommercialAccount.objects.create(user=self.worker, company=self.a, customer=self.customer)
        # The resolver also denies bad legacy/raw rows bypassing model.clean.
        CommercialAccount.objects.filter(pk=self.account.pk).update(customer=self.customer_b)
        with self.assertRaises(WebsiteError):
            accounts.active_account(self.worker, self.site.company_id)

    def test_database_enforces_user_company_uniqueness(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            CommercialAccount.objects.bulk_create([CommercialAccount(user=self.worker, company=self.a, customer=self.customer)])

    def test_current_suspension_customer_or_company_disable_revoke_access(self):
        self.verify()
        for field, value in (("status", "SUSPENDED"), ("status", "REVOKED")):
            CommercialAccount.objects.filter(pk=self.account.pk).update(**{field: value})
            with self.assertRaises(WebsiteError):
                accounts.resolve_commercial_account(self.worker, "a.catalog.test")
        CommercialAccount.objects.filter(pk=self.account.pk).update(status="ACTIVE")
        self.customer.active = False
        self.customer.save()
        with self.assertRaises(WebsiteError):
            accounts.resolve_commercial_account(self.worker, "a.catalog.test")

    def test_wholesale_only_admin_and_authorized_canonical_list_with_revocation(self):
        self.verify()
        SalesCustomerProfile.objects.create(customer=self.customer, price_list=self.price_list)
        with self.assertRaises(WebsiteAccessDenied):
            self.approve(user=self.editor)
        approved = self.approve()
        self.assertEqual(accounts.customer_price_list(approved).pk, self.price_list.pk)
        revoked = self.approve(approved=False)
        self.assertIsNone(accounts.customer_price_list(revoked))
        self.assertIsNone(accounts.customer_price_list(approved), "cached approval cannot survive revocation")
        accounts.resolve_commercial_account(self.worker, "a.catalog.test")

    def test_wholesale_does_not_fall_back_to_internal_or_foreign_list(self):
        self.verify()
        profile = SalesCustomerProfile.objects.create(customer=self.customer, price_list=self.foreign_list)
        with self.assertRaises(WebsiteError):
            self.approve()
        profile.price_list = self.price_list
        profile.save()
        self.approve()
        self.price_list.active = False
        self.price_list.save()
        self.account.refresh_from_db()
        with self.assertRaises(WebsiteError):
            accounts.customer_price_list(self.account)

    def test_customer_offer_uses_assigned_list_without_affecting_anonymous_prices(self):
        from apps.websites.catalog.quotation import recalculate_cart, recalculate_commercial_cart
        self.verify()
        wholesale = PriceList.objects.create(company=self.a, name="Customer wholesale", prices_include_tax=True)
        ProductPrice.objects.create(product=self.product, price_list=wholesale, amount="5", currency="PEN")
        SalesCustomerProfile.objects.create(customer=self.customer, price_list=wholesale)
        items = [{"productId": str(self.product.pk), "unitId": str(self.unit.pk), "quantity": 1}]
        self.assertEqual(recalculate_commercial_cart(self.worker, "a.catalog.test", items)["total"], "11.80")
        self.approve()
        self.assertEqual(recalculate_commercial_cart(self.worker, "a.catalog.test", items)["total"], "5.00")
        self.assertEqual(recalculate_cart("a.catalog.test", items)["total"], "11.80")
        ProductPrice.objects.filter(product=self.product, price_list=wholesale).delete()
        with self.assertRaises(WebsiteError):
            recalculate_commercial_cart(self.worker, "a.catalog.test", items)

    def test_stale_user_object_cannot_bypass_user_or_company_revocation(self):
        self.verify()
        type(self.worker).objects.filter(pk=self.worker.pk).update(is_active=False)
        with self.assertRaises(WebsiteError):
            accounts.active_account(self.worker, self.a.pk)
        type(self.worker).objects.filter(pk=self.worker.pk).update(is_active=True)
        type(self.a).objects.filter(pk=self.a.pk).update(is_active=False)
        with self.assertRaises(WebsiteError):
            accounts.active_account(self.worker, self.a.pk)
