"""Pruebas transaccionales de numeraciÃ³n concurrente de documentos de venta."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.inventory.models import Category, Product, Unit
from apps.partners.models import Customer, DocumentType
from apps.sales.models import DocumentSeries
from apps.sales.services import create_sales_document_draft, issue_sales_document


class SalesDocumentConcurrencyTest(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        company = Company.objects.create(name="Empresa concurrencia", ruc="20111111111")
        self.store = Store.objects.create(company=company, name="Principal")
        self.customer = Customer.objects.create(
            company=company,
            document_type="6",
            document_number="20222222222",
            legal_name="Cliente concurrencia",
        )
        self.series = DocumentSeries.objects.create(
            company=company, store=self.store, document_type=DocumentType.objects.get_or_create(code="01", defaults={"name": "01", "category": "INTERNAL"})[0], series="F900"
        )
        unit = Unit.objects.create(name="Unidad concurrencia", code="UCN")
        category = Category.objects.create(name="CategorÃ­a concurrencia")
        self.product = Product.objects.create(
            name="Producto concurrencia",
            sku="CONC-1",
            category=category,
            unit=unit,
            price_sale=Decimal("10"),
        )

    def _draft(self):
        return create_sales_document_draft(
            store_id=str(self.store.pk),
            customer=self.customer,
            document_type=DocumentType.objects.get_or_create(code="01", defaults={"name": "01", "category": "INTERNAL"})[0],
            series=self.series,
            lines=[{
                "product": self.product,
                "description": self.product.name,
                "quantity": Decimal("1"),
                "unit_price": Decimal("10"),
                "tax_type": "10",
                "igv_rate": Decimal("18"),
            }],
            issue_date=timezone.now().date(),
            register_inventory_movement=False,
        )

    def test_concurrent_issuance_assigns_unique_consecutive_numbers(self):
        document_ids = [self._draft().pk, self._draft().pk]
        barrier = Barrier(2)

        def emit(document_id):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                return issue_sales_document(document_id).number
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            numbers = list(executor.map(emit, document_ids))

        self.assertEqual(sorted(numbers), ["00000001", "00000002"])
        self.series.refresh_from_db()
        self.assertEqual(self.series.current_number, 2)

