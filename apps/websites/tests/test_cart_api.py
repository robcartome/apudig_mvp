from django.test import Client, TestCase
from apps.users.models import User
from apps.partners.models import Customer, SalesCustomerProfile
from apps.inventory.models import PriceList, ProductPrice
from apps.websites.models import CommercialAccount
from apps.websites.accounts import issue_email_challenge, verify_email_challenge, set_wholesale_approval
from apps.websites.commercial_sessions import start_session
from .test_catalog import CommercialCatalogFixture


class CommercialCartApiTest(CommercialCatalogFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.person = User.objects.create_user(email="quote-customer@integration.invalid", password="Synthetic-quote-password-2026!")
        self.customer = Customer.objects.create(company=self.a, document_type="0", legal_name="Quote customer")
        self.account = CommercialAccount.objects.create(user=self.person, company=self.a, customer=self.customer)
        proof = issue_email_challenge(self.person, self.site)
        verify_email_challenge(self.person, self.site, proof)
        tokens = start_session(self.person, "a.catalog.test")
        self.commercial = Client(HTTP_AUTHORIZATION="Bearer " + tokens["access"])
        self.items = [{"productId": str(self.product.pk), "unitId": str(self.unit.pk), "quantity": 1}]

    def endpoint(self, operation="quote", host="a.catalog.test"):
        return f"/api/v1/storefront/sites/{host}/account/cart/{operation}/"

    def post(self, data, operation="quote", client=None):
        return (client or self.commercial).post(self.endpoint(operation), data, content_type="application/json")

    def test_basic_and_wholesale_quotes_are_live_without_enabling_orders(self):
        basic = self.post({"items": self.items})
        self.assertEqual(basic.status_code, 200, basic.content)
        self.assertEqual(basic.json()["total"], "11.80")
        self.assertFalse(basic.json()["ordersEnabled"])
        price_list = PriceList.objects.create(company=self.a, name="Only customer", prices_include_tax=True)
        price = ProductPrice.objects.create(product=self.product, price_list=price_list, amount="5", currency="PEN")
        SalesCustomerProfile.objects.create(customer=self.customer, price_list=price_list)
        set_wholesale_approval(user=self.admin, company_id=self.a.pk, account_id=self.account.pk, approved=True)
        quote = self.post({"items": self.items}).json()
        self.assertEqual(quote["total"], "5.00")
        confirmed = self.post({"items": self.items, "offerFingerprint": quote["offerFingerprint"]}, "confirm")
        self.assertTrue(confirmed.json()["confirmed"])
        price.amount = "7"
        price.save()
        conflict = self.post({"items": self.items, "offerFingerprint": quote["offerFingerprint"]}, "confirm")
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["code"], "OFFER_CHANGED")
        self.site.refresh_from_db()
        self.assertEqual(self.site.editorial_revision, 1)

    def test_no_employee_or_anonymous_token_or_other_hostname_can_quote(self):
        self.assertEqual(self.post({"items": self.items}, client=self.authenticated(self.worker)).status_code, 401)
        self.assertEqual(self.post({"items": self.items}, client=Client()).status_code, 401)
        response = self.commercial.post(self.endpoint(host="b.catalog.test"), {"items": self.items}, content_type="application/json")
        self.assertEqual(response.status_code, 401)

    def test_tampering_and_unavailable_stock_reject_whole_offer(self):
        for data in ({"items": self.items, "company_id": str(self.b.pk)}, {"items": [{**self.items[0], "price": "0.01"}]}, {"items": [{**self.items[0], "quantity": True}]}, {"items": self.items * 2}):
            with self.subTest(data=data):
                self.assertEqual(self.post(data).status_code, 400)
        quote = self.post({"items": self.items}).json()
        self.stock.quantity = 0
        self.stock.save(update_fields=["quantity"])
        conflict = self.post({"items": self.items, "offerFingerprint": quote["offerFingerprint"]}, "confirm")
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["code"], "CART_UNAVAILABLE")

    def test_private_fields_and_client_selected_customer_are_not_returned_or_accepted(self):
        response = self.post({"items": self.items})
        self.assertIn("no-store", response["Cache-Control"])
        for field in ("priceList", "warehouse", "supplier", "purchase", "customerId", "stock"):
            self.assertNotIn(field, response.content.decode())
        self.assertEqual(self.post({"items": self.items, "customerId": str(self.customer.pk)}).status_code, 400)
