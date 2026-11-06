from django.test import TestCase

from apps.companies.models import Company
from apps.core.management.commands.seed import BRANDS, CATEGORIES, Command
from apps.inventory.models import Brand, Category, PriceList


class SeedCompanyScopeTest(TestCase):
    def test_inventory_masters_are_seeded_for_the_requested_company(self):
        company = Company.objects.create(name="Empresa A", ruc="20111111111")
        other_company = Company.objects.create(name="Empresa B", ruc="20222222222")
        command = Command()

        command._seed_categories(company)
        command._seed_brands(company)
        command._seed_price_lists(company)

        self.assertEqual(Category.objects.filter(company=company).count(), len(CATEGORIES))
        self.assertEqual(Brand.objects.filter(company=company).count(), len(BRANDS))
        self.assertEqual(PriceList.objects.filter(company=company).count(), 3)
        self.assertFalse(Category.objects.filter(company=other_company).exists())
        self.assertFalse(Brand.objects.filter(company=other_company).exists())
        self.assertFalse(PriceList.objects.filter(company=other_company).exists())
        self.assertFalse(Category.objects.filter(company__isnull=True).exists())
        self.assertFalse(Brand.objects.filter(company__isnull=True).exists())
        self.assertFalse(PriceList.objects.filter(company__isnull=True).exists())

