"""
inventory/tests/test_pricelists.py — Tests de listas de precio.
"""
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.companies.models import Company, Store
from apps.inventory.models import PriceList, Product, ProductPrice, Unit
from apps.inventory.services import (
    create_price_list,
    delete_product_price,
    set_product_price,
    toggle_price_list,
)

from django.contrib.auth import get_user_model
User = get_user_model()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_product(name="Prod PL", sku="SKU_PL1"):
    unit, _ = Unit.objects.get_or_create(name="Unidad PL", defaults={"code": "UPLX"})
    return Product.objects.create(
        name=name, sku=sku, unit=unit, price_sale=Decimal("10.00"), active=True
    )


# ── Servicios ─────────────────────────────────────────────────────────────────

class PriceListServiceTest(TestCase):

    def test_create_price_list(self):
        pl = create_price_list(name="Lista A", description="Desc A")
        self.assertEqual(pl.name, "Lista A")
        self.assertTrue(pl.active)

    def test_set_product_price_creates(self):
        pl = create_price_list(name="Lista B")
        p = _make_product()
        pp = set_product_price(pricelist_id=pl.pk, product_id=p.pk, amount=Decimal("25.00"))
        self.assertEqual(pp.amount, Decimal("25.00"))
        self.assertEqual(ProductPrice.objects.filter(price_list=pl, product=p).count(), 1)

    def test_set_product_price_updates_existing(self):
        pl = create_price_list(name="Lista C")
        p = _make_product(name="Prod PL C", sku="SKU_PL_C")
        set_product_price(pricelist_id=pl.pk, product_id=p.pk, amount=Decimal("10.00"))
        set_product_price(pricelist_id=pl.pk, product_id=p.pk, amount=Decimal("20.00"))
        self.assertEqual(ProductPrice.objects.filter(price_list=pl, product=p).count(), 1)
        pp = ProductPrice.objects.get(price_list=pl, product=p)
        self.assertEqual(pp.amount, Decimal("20.00"))

    def test_delete_product_price(self):
        pl = create_price_list(name="Lista D")
        p = _make_product(name="Prod PL D", sku="SKU_PL_D")
        set_product_price(pricelist_id=pl.pk, product_id=p.pk, amount=Decimal("5.00"))
        delete_product_price(pricelist_id=pl.pk, product_id=p.pk)
        self.assertEqual(ProductPrice.objects.filter(price_list=pl, product=p).count(), 0)

    def test_toggle_price_list(self):
        pl = create_price_list(name="Lista E")
        self.assertTrue(pl.active)
        toggle_price_list(pl)
        self.assertFalse(pl.active)
        toggle_price_list(pl)
        self.assertTrue(pl.active)


# ── Vistas ────────────────────────────────────────────────────────────────────

class PriceListViewsTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="pl@demo.com", password="pass1234")
        company = Company.objects.create(name="Empresa PL", ruc="20777777777")
        store = Store.objects.create(company=company, name="Tienda PL")
        session = self.client.session
        session["active_company_id"] = str(company.pk)
        session["active_store_id"] = str(store.pk)
        session.save()
        self.pl = create_price_list(name="Lista Test")
        self.product = _make_product()

    def _login(self):
        self.client.login(username="pl@demo.com", password="pass1234")

    def test_list_anonymous_redirect(self):
        resp = self.client.get(reverse("inventory:pricelist_list"))
        self.assertRedirects(resp, reverse("login"), fetch_redirect_response=False)

    def test_list_ok(self):
        self._login()
        resp = self.client.get(reverse("inventory:pricelist_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Lista Test")

    def test_create_get(self):
        self._login()
        resp = self.client.get(reverse("inventory:pricelist_create"))
        self.assertEqual(resp.status_code, 200)

    def test_create_post_ok(self):
        self._login()
        resp = self.client.post(
            reverse("inventory:pricelist_create"),
            {"name": "Lista Nueva", "description": "", "active": True},
        )
        self.assertEqual(PriceList.objects.filter(name="Lista Nueva").count(), 1)

    def test_detail_ok(self):
        self._login()
        resp = self.client.get(reverse("inventory:pricelist_detail", kwargs={"pk": self.pl.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Lista Test")

    def test_update_get(self):
        self._login()
        resp = self.client.get(reverse("inventory:pricelist_update", kwargs={"pk": self.pl.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_update_post_ok(self):
        self._login()
        resp = self.client.post(
            reverse("inventory:pricelist_update", kwargs={"pk": self.pl.pk}),
            {"name": "Lista Modificada", "description": "Nueva desc", "active": True},
        )
        self.pl.refresh_from_db()
        self.assertEqual(self.pl.name, "Lista Modificada")

    def test_toggle_post(self):
        self._login()
        self.client.post(reverse("inventory:pricelist_toggle", kwargs={"pk": self.pl.pk}))
        self.pl.refresh_from_db()
        self.assertFalse(self.pl.active)

    def test_del_price_post(self):
        self._login()
        set_product_price(pricelist_id=self.pl.pk, product_id=self.product.pk, amount=Decimal("15.00"))
        self.client.post(
            reverse("inventory:pricelist_del_price", kwargs={"pk": self.pl.pk}),
            {"product_id": str(self.product.pk)},
        )
        self.assertEqual(ProductPrice.objects.filter(price_list=self.pl, product=self.product).count(), 0)

    def test_set_prices_via_formset(self):
        self._login()
        data = {
            "prices-TOTAL_FORMS": "1",
            "prices-INITIAL_FORMS": "0",
            "prices-MIN_NUM_FORMS": "0",
            "prices-MAX_NUM_FORMS": "1000",
            "prices-0-product": str(self.product.pk),
            "prices-0-amount": "99.99",
            "prices-0-currency": "PEN",
        }
        self.client.post(reverse("inventory:pricelist_detail", kwargs={"pk": self.pl.pk}), data)
        pp = ProductPrice.objects.filter(price_list=self.pl, product=self.product).first()
        self.assertIsNotNone(pp)
        self.assertEqual(pp.amount, Decimal("99.99"))
