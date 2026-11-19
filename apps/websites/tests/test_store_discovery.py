from django.test import Client, TestCase
from apps.companies.models import UserCompanyAccess
from apps.users.models import UserStore
from .test_catalog import CommercialCatalogFixture


class StoreDiscoveryTest(CommercialCatalogFixture, TestCase):
    url = "/api/v1/auth/store-access/stores/me/"

    def test_admin_only_discovers_active_stores_of_current_company(self):
        result = self.client.get(self.url)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["store_ids"], [str(self.store.pk)])
        self.assertEqual(result.json()["stores"][0]["name"], self.store.name)
        self.assertIn("no-store", result["Cache-Control"])
        self.store.active = False
        self.store.save()
        self.assertEqual(self.client.get(self.url).json()["stores"], [])

    def test_worker_discovery_requires_current_assignment_and_membership(self):
        assignment = UserStore.objects.create(user=self.worker, store=self.store, role="SELLER")
        UserStore.objects.create(user=self.worker, store=self.foreign_store)
        client = self.authenticated(self.worker)
        self.assertEqual(client.get(self.url).json()["store_ids"], [str(self.store.pk)])
        assignment.is_active = False
        assignment.save()
        self.assertEqual(client.get(self.url).json()["store_ids"], [])
        UserCompanyAccess.objects.filter(user=self.worker).delete()
        self.assertEqual(client.get(self.url).status_code, 403)

    def test_no_anonymous_or_contextless_global_discovery(self):
        self.assertEqual(Client().get(self.url).status_code, 401)
        self.assertEqual(self.authenticated(self.worker, company_id=None).get(self.url).status_code, 403)

    def test_forged_foreign_store_context_is_rejected(self):
        client = self.authenticated(self.admin, store_id=str(self.foreign_store.pk))
        self.assertEqual(client.get(self.url).status_code, 403)
