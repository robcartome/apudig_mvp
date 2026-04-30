"""
inventory/tests/test_views.py — Tests de vistas de maestros.
"""
from django.test import TestCase
from django.urls import reverse

from apps.companies.models import Company, Store, UserCompanyAccess
from apps.inventory.models import Brand, Category, Unit
from apps.users.models import User


class MasterViewsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="test@demo.com", password="testpass")
        company = Company.objects.create(name="Demo SA", ruc="20999999901")
        store = Store.objects.create(company=company, name="Principal")
        UserCompanyAccess.objects.create(user=self.user, company=company, store=store, is_default=True)

        self.client.login(username="test@demo.com", password="testpass")
        session = self.client.session
        session["active_company_id"] = str(company.id)
        session["active_store_id"] = str(store.id)
        session.save()

    # ── Categories ────────────────────────────────────────────────────────────

    def test_category_list_ok(self):
        Category.objects.create(code="CAT1", name="Electrónica")
        resp = self.client.get(reverse("inventory:category_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Electrónica")

    def test_category_create_get(self):
        resp = self.client.get(reverse("inventory:category_create"))
        self.assertEqual(resp.status_code, 200)

    def test_category_create_post(self):
        resp = self.client.post(
            reverse("inventory:category_create"),
            {"code": "TECH", "name": "Tecnología", "active": True},
        )
        self.assertRedirects(resp, reverse("inventory:category_list"))
        self.assertTrue(Category.objects.filter(code="TECH").exists())

    def test_category_update(self):
        cat = Category.objects.create(code="OLD", name="Viejo")
        resp = self.client.post(
            reverse("inventory:category_update", args=[cat.pk]),
            {"code": "OLD", "name": "Nuevo nombre", "active": True},
        )
        self.assertRedirects(resp, reverse("inventory:category_list"))
        cat.refresh_from_db()
        self.assertEqual(cat.name, "Nuevo nombre")

    def test_category_delete(self):
        cat = Category.objects.create(code="DEL", name="Borrar")
        resp = self.client.post(reverse("inventory:category_delete", args=[cat.pk]))
        self.assertRedirects(resp, reverse("inventory:category_list"))
        self.assertFalse(Category.objects.filter(pk=cat.pk).exists())

    def test_category_list_search(self):
        Category.objects.create(code="A", name="Alpha")
        Category.objects.create(code="B", name="Beta")
        resp = self.client.get(reverse("inventory:category_list") + "?q=alpha")
        self.assertContains(resp, "Alpha")
        self.assertNotContains(resp, "Beta")

    # ── Brands ────────────────────────────────────────────────────────────────

    def test_brand_create_post(self):
        resp = self.client.post(
            reverse("inventory:brand_create"),
            {"name": "Samsung", "active": True},
        )
        self.assertRedirects(resp, reverse("inventory:brand_list"))
        self.assertTrue(Brand.objects.filter(name="Samsung").exists())

    # ── Units ─────────────────────────────────────────────────────────────────

    def test_unit_list_ok(self):
        Unit.objects.create(code="UND", name="Unidad")
        resp = self.client.get(reverse("inventory:unit_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Unidad")

    def test_unit_create_post(self):
        resp = self.client.post(
            reverse("inventory:unit_create"),
            {"code": "KG", "name": "Kilogramo"},
        )
        self.assertRedirects(resp, reverse("inventory:unit_list"))
        self.assertTrue(Unit.objects.filter(code="KG").exists())

    # ── Redirect if not logged in ──────────────────────────────────────────────

    def test_category_list_redirects_anonymous(self):
        self.client.logout()
        resp = self.client.get(reverse("inventory:category_list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])
