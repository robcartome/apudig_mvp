"""
partners/tests/test_services.py — Tests de servicios de partners.
"""
from django.test import TestCase

from apps.partners.models import CoreCustomer
from apps.partners.services import create_customer
from apps.partners.selectors import get_customer_by_document, search_customers


class CreateCustomerTest(TestCase):
    def test_create_customer_ok(self):
        c = create_customer(
            document_type="6",
            document_number="20123456789",
            legal_name="Demo SAC",
        )
        self.assertIsNotNone(c.pk)
        self.assertEqual(c.legal_name, "Demo SAC")

    def test_get_by_document(self):
        create_customer("6", "20000000001", "Test Corp")
        found = get_customer_by_document("6", "20000000001")
        self.assertIsNotNone(found)

    def test_search_customers(self):
        create_customer("1", "12345678", "Juan Pérez")
        results = search_customers("Juan")
        self.assertEqual(results.count(), 1)
