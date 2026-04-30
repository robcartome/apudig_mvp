"""
companies/tests/test_models.py — Tests de modelos de empresa.
"""
from django.test import TestCase

from apps.companies.models import Company, CompanyBranding, Store


class CompanyModelTest(TestCase):
    def test_str(self):
        company = Company(name="Ferretería Demo", ruc="12345678901")
        self.assertEqual(str(company), "Ferretería Demo")


class CompanyBrandingModelTest(TestCase):
    def test_branding_links_to_company(self):
        company = Company.objects.create(name="Demo", ruc="20999999999")
        branding = CompanyBranding.objects.create(
            company=company, primary_color="#FF0000"
        )
        self.assertEqual(branding.company, company)
        self.assertEqual(company.branding, branding)
