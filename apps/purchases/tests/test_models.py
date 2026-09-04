from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.companies.models import Company, Store
from apps.inventory.models import Product, Unit
from apps.partners.models import DocumentType, Supplier
from apps.purchases.models import (
    PurchaseDocument,
    PurchaseDocumentLine,
    PurchaseDocumentStatus,
    PurchasePaymentStatus,
)


class PurchaseDocumentModelTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Empresa compras", ruc="20111111111")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.supplier = Supplier.objects.create(
            company=self.company, name="Proveedor SAC", document_number="20222222222"
        )
        self.document_type = DocumentType.objects.create(
            code="01-C", name="Factura de compra", category="BILLING"
        )
        self.unit = Unit.objects.create(code="UND-C", name="Unidad compra")
        self.product = Product.objects.create(
            company=self.company,
            name="Producto compra",
            sku="COMPRA-1",
            unit=self.unit,
        )

    def make_document(self, **overrides):
        values = {
            "company": self.company,
            "store": self.store,
            "supplier": self.supplier,
            "document_type": self.document_type,
            "supplier_document_number": self.supplier.document_number,
            "supplier_name": self.supplier.name,
            "series": "F001",
            "number": "123",
            "issue_date": date(2026, 8, 31),
        }
        values.update(overrides)
        return PurchaseDocument.objects.create(**values)

    def test_document_and_payment_status_are_independent(self):
        document = self.make_document()
        self.assertEqual(document.document_status, PurchaseDocumentStatus.DRAFT)
        self.assertEqual(document.payment_status, PurchasePaymentStatus.UNPAID)
        document.document_status = PurchaseDocumentStatus.REGISTERED
        document.save(update_fields=["document_status"])
        document.refresh_from_db()
        self.assertEqual(document.payment_status, PurchasePaymentStatus.UNPAID)

    def test_document_does_not_require_order_or_inventory_movement(self):
        document = self.make_document(register_inventory_movement=False)
        self.assertFalse(document.register_inventory_movement)
        self.assertIsNone(document.purchase_order_id)
        self.assertFalse(hasattr(document, "inventory_movement_id"))

    def test_supplier_document_identity_is_unique_per_company_and_supplier(self):
        self.make_document()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_document()

    def test_blank_number_allows_informal_documents(self):
        self.make_document(series="", number="")
        self.make_document(series="", number="")
        self.assertEqual(PurchaseDocument.objects.count(), 2)

    def test_rejects_supplier_from_another_company(self):
        other_company = Company.objects.create(name="Otra", ruc="20333333333")
        supplier = Supplier.objects.create(
            company=other_company, name="Proveedor externo", document_number="20444444444"
        )
        document = self.make_document(supplier=supplier)
        with self.assertRaises(ValidationError):
            document.full_clean()

    def test_line_keeps_invoiced_price_and_defaults_to_update_current_price(self):
        document = self.make_document()
        line = PurchaseDocumentLine.objects.create(
            purchase_document=document,
            position=1,
            product=self.product,
            description="Precio facturado",
            quantity=Decimal("2"),
            unit=self.unit,
            unit_code=self.unit.code,
            unit_price=Decimal("13.456789"),
        )
        self.product.price_purchase = Decimal("99.00")
        self.product.save(update_fields=["price_purchase"])
        line.refresh_from_db()
        self.assertEqual(line.unit_price, Decimal("13.456789"))
        self.assertTrue(line.update_purchase_price)

    def test_non_inventory_product_can_be_used_on_purchase_line(self):
        self.product.tracks_inventory = False
        self.product.save(update_fields=["tracks_inventory"])
        line = PurchaseDocumentLine(
            purchase_document=self.make_document(),
            position=1,
            product=self.product,
            description="Servicio",
            quantity=Decimal("1"),
            unit=self.unit,
            unit_code=self.unit.code,
            unit_price=Decimal("100"),
        )
        line.full_clean()
