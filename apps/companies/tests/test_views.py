from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from apps.companies.models import Company, Store, UserCompanyAccess
from apps.users.models import UserStore


User = get_user_model()


class UserCompanyAccessConstraintTest(TestCase):
    def test_only_one_company_level_access_is_allowed_per_user_and_company(self):
        user = User.objects.create_user(email="user@example.com", password="secret")
        company = Company.objects.create(name="Empresa", ruc="20123456789")
        UserCompanyAccess.objects.create(user=user, company=company, store=None)

        with self.assertRaises(IntegrityError), transaction.atomic():
            UserCompanyAccess.objects.create(user=user, company=company, store=None)

        self.assertEqual(
            UserCompanyAccess.objects.filter(
                user=user,
                company=company,
                store__isnull=True,
            ).count(),
            1,
        )


class SelectCompanyViewTest(TestCase):
    def setUp(self):
        self.company_a = Company.objects.create(name="Empresa A", ruc="20111111111")
        self.company_b = Company.objects.create(name="Empresa B", ruc="20222222222")
        self.store_a = Store.objects.create(company=self.company_a, name="Sucursal A")
        self.store_b = Store.objects.create(company=self.company_b, name="Sucursal B")
        self.superuser_a = User.objects.create_superuser(
            email="admin-a@example.com",
            password="secret",
        )
        self.superuser_b = User.objects.create_superuser(
            email="admin-b@example.com",
            password="secret",
        )

    def test_multiple_superusers_are_synchronized_independently(self):
        for user in (self.superuser_a, self.superuser_b):
            client = Client()
            client.force_login(user)

            response = client.get(reverse("select_company"))

            self.assertEqual(response.status_code, 200)
            self.assertEqual(UserCompanyAccess.objects.filter(user=user).count(), 4)
            visible_accesses = list(response.context["accesses"])
            self.assertEqual(len(visible_accesses), 2)
            self.assertTrue(all(access.store_id for access in visible_accesses))

    def test_repeated_visits_do_not_create_duplicate_accesses(self):
        self.client.force_login(self.superuser_a)

        self.client.get(reverse("select_company"))
        self.client.get(reverse("select_company"))

        self.assertEqual(
            UserCompanyAccess.objects.filter(user=self.superuser_a).count(),
            4,
        )

    def test_company_level_option_is_hidden_when_store_access_exists(self):
        user = User.objects.create_user(email="regular@example.com", password="secret")
        company_without_stores = Company.objects.create(
            name="Empresa sin sucursales",
            ruc="20333333333",
        )
        UserCompanyAccess.objects.create(user=user, company=self.company_a, store=None)
        store_access = UserCompanyAccess.objects.create(
            user=user,
            company=self.company_a,
            store=self.store_a,
        )
        UserStore.objects.create(user=user, store=self.store_a, role="SELLER")
        company_only_access = UserCompanyAccess.objects.create(
            user=user,
            company=company_without_stores,
            store=None,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("select_company"))

        self.assertEqual(response.status_code, 200)
        visible_ids = {access.pk for access in response.context["accesses"]}
        self.assertEqual(visible_ids, {store_access.pk, company_only_access.pk})

    def test_both_selectors_show_only_the_stores_assigned_to_the_user(self):
        user = User.objects.create_user(email="seller@example.com", password="secret")
        assigned_access = UserCompanyAccess.objects.create(
            user=user,
            company=self.company_a,
            store=self.store_a,
        )
        unauthorized_access = UserCompanyAccess.objects.create(
            user=user,
            company=self.company_b,
            store=self.store_b,
        )
        UserStore.objects.create(user=user, store=self.store_a, role="SELLER")

        company_c = Company.objects.create(name="Empresa C", ruc="20444444444")
        store_c = Store.objects.create(company=company_c, name="Sucursal C")
        second_assigned_access = UserCompanyAccess.objects.create(
            user=user,
            company=company_c,
            store=store_c,
        )
        UserStore.objects.create(user=user, store=store_c, role="CASHIER")
        self.client.force_login(user)

        response = self.client.get(reverse("select_company"))

        self.assertEqual(response.status_code, 200)
        expected_ids = {assigned_access.pk, second_assigned_access.pk}
        self.assertEqual(
            {access.pk for access in response.context["accesses"]},
            expected_ids,
        )
        self.assertEqual(
            {access.pk for access in response.context["available_accesses"]},
            expected_ids,
        )
        self.assertNotIn(
            unauthorized_access.pk,
            {access.pk for access in response.context["accesses"]},
        )

    def test_post_rejects_an_access_not_assigned_to_the_user(self):
        user = User.objects.create_user(email="cashier@example.com", password="secret")
        unauthorized_access = UserCompanyAccess.objects.create(
            user=user,
            company=self.company_b,
            store=self.store_b,
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("select_company"),
            {"access_id": unauthorized_access.pk},
        )

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("active_company_id", self.client.session)
        self.assertNotIn("active_store_id", self.client.session)

    def test_inactive_company_and_store_are_not_selectable(self):
        user = User.objects.create_user(email="active@example.com", password="secret")
        active_access = UserCompanyAccess.objects.create(
            user=user,
            company=self.company_a,
            store=self.store_a,
        )
        UserStore.objects.create(user=user, store=self.store_a, role="SELLER")

        inactive_store = Store.objects.create(
            company=self.company_a,
            name="Sucursal inactiva",
            active=False,
        )
        inactive_store_access = UserCompanyAccess.objects.create(
            user=user,
            company=self.company_a,
            store=inactive_store,
        )
        UserStore.objects.create(user=user, store=inactive_store, role="ADMIN")

        self.company_b.is_active = False
        self.company_b.save(update_fields=["is_active"])
        inactive_company_access = UserCompanyAccess.objects.create(
            user=user,
            company=self.company_b,
            store=self.store_b,
        )
        UserStore.objects.create(user=user, store=self.store_b, role="SELLER")

        company_c = Company.objects.create(name="Empresa C", ruc="20555555555")
        store_c = Store.objects.create(company=company_c, name="Sucursal C")
        second_active_access = UserCompanyAccess.objects.create(
            user=user,
            company=company_c,
            store=store_c,
        )
        UserStore.objects.create(user=user, store=store_c, role="SELLER")
        self.client.force_login(user)

        response = self.client.get(reverse("select_company"))

        self.assertEqual(response.status_code, 200)
        visible_ids = {access.pk for access in response.context["accesses"]}
        self.assertEqual(visible_ids, {active_access.pk, second_active_access.pk})
        self.assertNotIn(inactive_store_access.pk, visible_ids)
        self.assertNotIn(inactive_company_access.pk, visible_ids)
