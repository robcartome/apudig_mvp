from datetime import date
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.core.models import AuditLog
from apps.inventory.models import (
    Movement,
    MovementOrigin,
    MovementStatus,
    Product,
    ProductSupplier,
    ProductUnit,
    StockByWarehouse,
    Unit,
    Warehouse,
)
from apps.inventory.selectors import get_movement_traceability_report
from apps.inventory.services import confirm_movement, register_entry
from apps.partners.models import DocumentType, Supplier
from apps.purchases.models import PurchaseCategory, PurchaseDeliveryStatus, PurchaseDocumentStatus
from apps.purchases.selectors import get_purchase_price_history
from apps.purchases.services import (
    cancel_purchase_document,
    create_purchase_document_draft,
    register_purchase_document,
    update_purchase_document_draft,
)


class PurchaseDocumentServiceTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Empresa servicio compras", ruc="20511111111")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.supplier = Supplier.objects.create(company=self.company, name="Proveedor Uno", document_number="20522222222")
        self.document_type = DocumentType.objects.create(code="FC-S", name="Factura compra", category="BILLING")
        self.unit = Unit.objects.create(code="UCS", name="Unidad compras service")
        self.product = Product.objects.create(company=self.company, name="Articulo", sku="PCS-1", unit=self.unit)
        self.warehouse = Warehouse.objects.create(store=self.store, name="Almacen compras")

    def line(self, **overrides):
        values = {"product": self.product, "description": "Articulo facturado", "quantity": Decimal("2"), "unit_price": Decimal("100"), "tax_type": "10", "igv_rate": Decimal("18")}
        values.update(overrides)
        return values

    def create(self, **overrides):
        values = {"company_id": self.company.pk, "store": self.store, "supplier": self.supplier, "document_type": self.document_type, "lines": [self.line()], "series": "F001", "number": "10", "issue_date": date(2026, 9, 1), "register_inventory_movement": False}
        values.update(overrides)
        return create_purchase_document_draft(**values)

    def test_create_calculates_totals_and_supplier_snapshot(self):
        document = self.create()
        self.assertEqual(document.taxable_amount, Decimal("200.00"))
        self.assertEqual(document.igv_total, Decimal("36.00"))
        self.assertEqual(document.total, Decimal("236.00"))
        self.assertEqual(document.supplier_name, self.supplier.name)
        self.assertFalse(document.register_inventory_movement)
        self.assertTrue(AuditLog.objects.filter(entity="PurchaseDocument", action="CREATE").exists())

    def test_update_recalculates_and_replaces_lines(self):
        document = self.create()
        update_purchase_document_draft(document.pk, company_id=self.company.pk, store=self.store, supplier=self.supplier, document_type=self.document_type, lines=[self.line(quantity=Decimal("3"), unit_price=Decimal("10"))], series="F001", number="10", issue_date=date(2026, 9, 1))
        document.refresh_from_db()
        self.assertEqual(document.lines.count(), 1)
        self.assertEqual(document.total, Decimal("35.40"))

    def test_registered_document_cannot_be_edited(self):
        document = self.create()
        register_purchase_document(document.pk, company_id=self.company.pk)
        document.refresh_from_db()
        self.assertEqual(document.document_status, PurchaseDocumentStatus.REGISTERED)
        with self.assertRaisesRegex(ValueError, "borrador"):
            update_purchase_document_draft(document.pk, company_id=self.company.pk, store=self.store, supplier=self.supplier, document_type=self.document_type, lines=[self.line()], issue_date=date(2026, 9, 1))

    def test_rejects_product_from_another_company(self):
        other = Company.objects.create(name="Otra empresa", ruc="20533333333")
        foreign = Product.objects.create(company=other, name="Ajeno", sku="FOREIGN", unit=self.unit)
        with self.assertRaisesRegex(ValueError, "producto"):
            self.create(lines=[self.line(product=foreign)])

    def test_register_creates_confirmed_entry_and_increases_stock(self):
        document = self.create(
            register_inventory_movement=True,
            warehouse=self.warehouse,
        )
        register_purchase_document(document.pk, company_id=self.company.pk)
        movement = document.inventory_movements.get(origin=MovementOrigin.PURCHASE)
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal("2"))
        self.assertEqual(movement.type, "ENTRY")
        self.assertEqual(movement.status, MovementStatus.CONFIRMED)
        self.assertEqual(movement.purchase_document_id, document.pk)
        report = get_movement_traceability_report(str(self.store.pk))
        self.assertEqual(report["products"][0]["entries"][0]["purchase_document_id"], str(document.pk))

    def test_register_without_warehouse_rolls_back_document_status(self):
        document = self.create(register_inventory_movement=True)
        with self.assertRaisesRegex(ValueError, "almacen"):
            register_purchase_document(document.pk, company_id=self.company.pk)
        document.refresh_from_db()
        self.assertEqual(document.document_status, PurchaseDocumentStatus.DRAFT)
        self.assertFalse(Movement.objects.exists())

    def test_invoice_is_pending_when_goods_have_not_been_received(self):
        document = self.create(register_inventory_movement=False)

        register_purchase_document(document.pk, company_id=self.company.pk)

        document.refresh_from_db()
        self.assertEqual(document.delivery_status, PurchaseDeliveryStatus.PENDING)

    def test_invoice_matches_a_previous_inventory_entry_without_duplicate_stock(self):
        entry = register_entry(
            store_id=str(self.store.pk), warehouse_id=str(self.warehouse.pk),
            date=timezone.now(),
            lines=[{
                "product_id": self.product.pk, "quantity": Decimal("2"),
                "unit_id": self.unit.pk, "unit_price": Decimal("100"),
            }],
            supplier=self.supplier, origin=MovementOrigin.MANUAL,
            reason="Guía de remisión GR-001", created_by=None,
        )
        confirm_movement(entry)
        document = self.create(
            register_inventory_movement=False,
            receipt_movements=[entry],
        )

        register_purchase_document(document.pk, company_id=self.company.pk)

        document.refresh_from_db()
        self.assertEqual(document.delivery_status, PurchaseDeliveryStatus.RECEIVED)
        self.assertEqual(document.lines.get().receipt_matches.count(), 1)
        self.assertEqual(Movement.objects.count(), 1)

    def test_non_inventory_purchase_registers_without_movement(self):
        self.product.tracks_inventory = False
        self.product.save(update_fields=["tracks_inventory"])
        document = self.create(register_inventory_movement=True)
        register_purchase_document(document.pk, company_id=self.company.pk)
        document.refresh_from_db()
        self.assertEqual(document.document_status, PurchaseDocumentStatus.REGISTERED)
        self.assertFalse(document.inventory_movements.exists())

    def test_expense_category_registers_without_inventory_movement(self):
        category = PurchaseCategory.objects.create(
            company=self.company, code="SERV", name="Servicios profesionales"
        )
        document = self.create(
            register_inventory_movement=True,
            lines=[self.line(product=None, purchase_category=category, description="Asesoria")],
        )
        register_purchase_document(document.pk, company_id=self.company.pk)
        document.refresh_from_db()
        line = document.lines.get()
        self.assertEqual(document.document_status, PurchaseDocumentStatus.REGISTERED)
        self.assertEqual(line.purchase_category, category)
        self.assertIsNone(line.product)
        self.assertIsNone(line.unit)
        self.assertEqual(line.stock_quantity, Decimal("0"))
        self.assertFalse(Movement.objects.exists())

    def test_rejects_purchase_category_from_another_company(self):
        other = Company.objects.create(name="Empresa categoria ajena", ruc="20544444444")
        category = PurchaseCategory.objects.create(company=other, code="AJENA", name="Ajena")
        with self.assertRaisesRegex(ValueError, "categoria"):
            self.create(lines=[self.line(product=None, purchase_category=category)])

    def test_cancel_registered_purchase_reverses_stock(self):
        document = self.create(register_inventory_movement=True, warehouse=self.warehouse)
        register_purchase_document(document.pk, company_id=self.company.pk)
        cancel_purchase_document(document.pk, company_id=self.company.pk)
        document.refresh_from_db()
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        original = document.inventory_movements.get(origin=MovementOrigin.PURCHASE)
        self.assertEqual(document.document_status, PurchaseDocumentStatus.CANCELLED)
        self.assertEqual(stock.quantity, Decimal("0"))
        self.assertEqual(original.reversal.origin, MovementOrigin.PURCHASE_REVERSAL)
        self.assertEqual(original.reversal.purchase_document_id, document.pk)

    def test_register_updates_product_and_existing_supplier_price(self):
        relation = ProductSupplier.objects.create(
            product=self.product,
            supplier=self.supplier,
            purchase_price=Decimal("1"),
        )
        document = self.create(lines=[self.line(unit_price=Decimal("25.123456"))])
        historical_line = document.lines.get()
        register_purchase_document(document.pk, company_id=self.company.pk)
        self.product.refresh_from_db()
        relation.refresh_from_db()
        historical_line.refresh_from_db()
        self.assertEqual(self.product.price_purchase, Decimal("25.12"))
        self.assertEqual(relation.purchase_price, Decimal("25.123456"))
        self.assertEqual(historical_line.unit_price, Decimal("25.123456"))

    def test_line_can_disable_current_price_update(self):
        self.product.price_purchase = Decimal("9.00")
        self.product.save(update_fields=["price_purchase"])
        document = self.create(lines=[self.line(unit_price=Decimal("50"), update_purchase_price=False)])
        register_purchase_document(document.pk, company_id=self.company.pk)
        self.product.refresh_from_db()
        self.assertEqual(self.product.price_purchase, Decimal("9.00"))

    def test_purchase_unit_and_currency_are_converted_to_base_pen_price(self):
        box = Unit.objects.create(code="BCS", name="Caja compras")
        ProductUnit.objects.create(
            product=self.product,
            unit=box,
            conversion_factor=Decimal("10"),
            is_default_purchase=True,
        )
        document = self.create(
            currency="USD",
            exchange_rate=Decimal("3.75"),
            lines=[self.line(unit=box, unit_price=Decimal("100"))],
        )
        register_purchase_document(document.pk, company_id=self.company.pk)
        self.product.refresh_from_db()
        self.assertEqual(self.product.price_purchase, Decimal("37.50"))

    def test_price_history_compares_with_previous_registered_purchase(self):
        first = self.create(lines=[self.line(unit_price=Decimal("10"))])
        register_purchase_document(first.pk, company_id=self.company.pk)
        second = self.create(number="11", lines=[self.line(unit_price=Decimal("12"))])
        register_purchase_document(second.pk, company_id=self.company.pk)
        rows = get_purchase_price_history(self.company.pk, self.store.pk)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["document"].pk, second.pk)
        self.assertEqual(rows[0]["previous_price"], Decimal("10"))
        self.assertEqual(rows[0]["variance"], Decimal("2"))
        self.assertEqual(rows[0]["variance_percent"], Decimal("20"))
