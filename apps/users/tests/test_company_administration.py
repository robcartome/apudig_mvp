from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.companies.models import Company, Store, UserCompanyAccess
from apps.users.models import Role, UserRole, UserStore


User = get_user_model()


class CompanyAdministrationAuthorizationTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Empresa A", ruc="20111111111")
        self.other_company = Company.objects.create(name="Empresa B", ruc="20222222222")
        self.store_a = Store.objects.create(company=self.company, name="Tienda A")
        self.store_b = Store.objects.create(company=self.company, name="Tienda B")
        self.other_store = Store.objects.create(company=self.other_company, name="Tienda Externa")
        self.admin_role = Role.objects.create(name="ADMIN", description="Administrador")
        self.seller_role = Role.objects.create(name="SELLER", description="Vendedor")
        self.company_admin = User.objects.create_user(
            email="admin@empresa.test",
            password="secret",
        )
        self.seller = User.objects.create_user(
            email="seller@empresa.test",
            password="secret",
        )
        self.outsider = User.objects.create_user(
            email="outsider@empresa.test",
            password="secret",
        )
        UserRole.objects.create(
            user=self.company_admin,
            company=self.company,
            role=self.admin_role,
        )
        UserRole.objects.create(
            user=self.seller,
            company=self.company,
            role=self.seller_role,
        )
        UserCompanyAccess.objects.create(
            user=self.company_admin,
            company=self.company,
            store=self.store_a,
        )
        UserCompanyAccess.objects.create(
            user=self.seller,
            company=self.company,
            store=self.store_a,
        )
        UserStore.objects.create(user=self.seller, store=self.store_a, role="SELLER")

    def activate(self, user, company=None, store=None):
        self.client.force_login(user)
        session = self.client.session
        session["active_company_id"] = str((company or self.company).pk)
        session["active_store_id"] = str((store or self.store_a).pk)
        session.save()

    def test_non_staff_company_admin_can_open_management(self):
        self.assertFalse(self.company_admin.is_staff)
        self.activate(self.company_admin)

        response = self.client.get(reverse("users:user_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.seller.email)
        self.assertNotContains(response, self.outsider.email)
        self.assertContains(response, reverse("users:admin_panel"))

    def test_seller_cannot_open_management(self):
        self.activate(self.seller)

        response = self.client.get(reverse("users:user_list"))

        self.assertEqual(response.status_code, 403)

        dashboard = self.client.get(reverse("dashboard"))
        self.assertNotContains(dashboard, reverse("users:admin_panel"))

    def test_store_admin_has_full_store_scope_but_not_company_management(self):
        store_admin = User.objects.create_user(
            email="store-admin@empresa.test",
            password="secret",
        )
        UserCompanyAccess.objects.create(
            user=store_admin,
            company=self.company,
            store=self.store_a,
        )
        UserStore.objects.create(user=store_admin, store=self.store_a, role="ADMIN")
        self.activate(store_admin)

        response = self.client.get(reverse("users:user_list"))

        self.assertEqual(response.status_code, 403)
        dashboard = self.client.get(reverse("dashboard"))
        self.assertNotContains(dashboard, reverse("users:admin_panel"))

    def test_company_admin_cannot_manage_platform_role_catalog(self):
        self.activate(self.company_admin)

        response = self.client.get(reverse("users:role_list"))

        self.assertEqual(response.status_code, 403)

    def test_user_api_is_company_scoped_and_rejects_sellers(self):
        self.activate(self.seller)
        denied = self.client.get(reverse("api_v1_auth_users"))
        self.assertEqual(denied.status_code, 403)

        self.client.logout()
        self.activate(self.company_admin)
        response = self.client.get(reverse("api_v1_auth_users"))

        self.assertEqual(response.status_code, 200)
        emails = {item["email"] for item in response.json()}
        self.assertIn(self.seller.email, emails)
        self.assertNotIn(self.outsider.email, emails)

    def test_company_admin_cannot_create_global_roles_through_api(self):
        self.activate(self.company_admin)

        response = self.client.post(
            reverse("api_v1_auth_roles"),
            {"name": "UNAUTHORIZED_ROLE", "description": "No permitido"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Role.objects.filter(name="UNAUTHORIZED_ROLE").exists())

    def test_company_admin_cannot_edit_another_company(self):
        self.activate(self.company_admin)

        response = self.client.get(
            reverse("users:company_edit", args=[self.other_company.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_assigning_company_admin_grants_every_store_in_company(self):
        target = User.objects.create_user(email="target@empresa.test", password="secret")
        UserCompanyAccess.objects.create(
            user=target,
            company=self.company,
            store=None,
        )
        self.activate(self.company_admin)

        response = self.client.post(
            reverse("users:user_detail", args=[target.pk]),
            {"save_roles": "1", "role_ids": [str(self.admin_role.pk)]},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            UserRole.objects.filter(
                user=target,
                company=self.company,
                role=self.admin_role,
            ).exists()
        )
        self.assertEqual(
            set(UserStore.objects.filter(user=target).values_list("store_id", flat=True)),
            {self.store_a.pk, self.store_b.pk},
        )
        self.assertFalse(
            UserStore.objects.filter(user=target, store=self.other_store).exists()
        )

    def test_store_access_saves_branch_role_without_crossing_company(self):
        target = User.objects.create_user(email="cashier@empresa.test", password="secret")
        UserCompanyAccess.objects.create(user=target, company=self.company, store=None)
        self.activate(self.company_admin)

        response = self.client.post(
            f"{reverse('users:user_detail', args=[target.pk])}?tab=accesos",
            {
                "save_accesos": "1",
                "access": [
                    f"{self.company.pk}|{self.store_b.pk}",
                    f"{self.other_company.pk}|{self.other_store.pk}",
                ],
                f"store_role_{self.store_b.pk}": "CASHIER",
                f"store_role_{self.other_store.pk}": "ADMIN",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            UserStore.objects.filter(
                user=target,
                store=self.store_b,
                role="CASHIER",
            ).exists()
        )
        self.assertFalse(
            UserStore.objects.filter(user=target, store=self.other_store).exists()
        )

    def test_company_admin_can_render_store_access_tab(self):
        self.activate(self.company_admin)

        response = self.client.get(
            f"{reverse('users:user_detail', args=[self.seller.pk])}?tab=accesos"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin tienda")
        self.assertContains(response, self.store_a.name)

    def test_spoofed_store_session_is_cleared(self):
        self.activate(self.seller, company=self.other_company, store=self.other_store)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("select_company"))
        self.assertNotIn("active_company_id", self.client.session)

    def test_company_admin_cannot_spoof_a_store_from_another_company(self):
        self.activate(
            self.company_admin,
            company=self.company,
            store=self.other_store,
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("select_company"))

    def test_company_admin_removes_only_membership_in_active_company(self):
        target = User.objects.create_user(email="multi@empresa.test", password="secret")
        UserCompanyAccess.objects.create(
            user=target,
            company=self.company,
            store=self.store_a,
        )
        UserStore.objects.create(user=target, store=self.store_a, role="SELLER")
        other_access = UserCompanyAccess.objects.create(
            user=target,
            company=self.other_company,
            store=self.other_store,
        )
        UserStore.objects.create(user=target, store=self.other_store, role="SELLER")
        self.activate(self.company_admin)

        response = self.client.post(
            reverse("users:user_delete", args=[target.pk]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(pk=target.pk).exists())
        self.assertTrue(UserCompanyAccess.objects.filter(pk=other_access.pk).exists())
        self.assertFalse(
            UserCompanyAccess.objects.filter(user=target, company=self.company).exists()
        )
