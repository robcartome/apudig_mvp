"""
sales/tests/test_services.py — Tests del servicio de ventas.
"""
from decimal import Decimal

from django.test import TestCase

from apps.companies.models import Company, Store
from apps.partners.models import CoreCustomer
from apps.sales.models import DocumentSeries, SalesQuotation
from apps.sales.services import create_quotation, get_or_create_series


class QuotationServiceTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Demo", ruc="20000000002")
        self.store = Store.objects.create(company=self.company, name="Tienda 1")
        self.customer = CoreCustomer.objects.create(
            company=self.company,
            document_type="6",
            document_number="20888888888",
            legal_name="Cliente Test SAC",
        )
        self.series = get_or_create_series(
            company_id=str(self.company.id),
            store_id=str(self.store.id),
            voucher_type="COT",
            series_code="C001",
        )

    def test_create_quotation_assigns_number(self):
        from django.utils import timezone
        q = create_quotation(
            store_id=str(self.store.id),
            customer=self.customer,
            series=self.series,
            lines=[],
            issue_date=timezone.now().date(),
        )
        self.assertEqual(q.number, 1)
        self.assertEqual(q.series_code, "C001")

    def test_series_number_increments(self):
        from django.utils import timezone
        d = timezone.now().date()
        q1 = create_quotation(str(self.store.id), self.customer, self.series, [], issue_date=d)
        q2 = create_quotation(str(self.store.id), self.customer, self.series, [], issue_date=d)
        self.assertEqual(q2.number, q1.number + 1)
