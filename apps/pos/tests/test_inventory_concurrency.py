"""Pruebas concurrentes de stock para ventas POS."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase

from apps.companies.models import Company, Store
from apps.inventory.models import (
    Movement,
    MovementOrigin,
    Product,
    ProductUnit,
    StockByWarehouse,
    Unit,
    Warehouse,
)
from apps.partners.models import Customer, DocumentType
from apps.pos.models import PosRegister, PosTransaction
from apps.pos.services import PosDomainError, checkout_pos_sale, open_cash_session
from apps.sales.models import DocumentSeries, MeansOfPayment, SalesDocument
from apps.users.models import User


class PosInventoryConcurrencyTest(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.company = Company.objects.create(
            name="Ferretería POS concurrente",
            ruc="20101010101",
        )
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.user = User.objects.create_user(email="concurrente@pos.test", password="test")
        self.customer = Customer.objects.create(
            company=self.company,
            document_type="1",
            document_number="44556677",
            legal_name="Cliente concurrente",
        )
        self.unit = Unit.objects.create(code="UC1", name="Unidad concurrente")
        self.product = Product.objects.create(
            company=self.company,
            name="Última unidad",
            sku="ULT-001",
            unit=self.unit,
            price_sale=Decimal("10.00"),
            tracks_inventory=True,
        )
        ProductUnit.objects.create(
            product=self.product,
            unit=self.unit,
            conversion_factor=1,
            is_default_sale=True,
            is_default_purchase=True,
        )
        self.warehouse = Warehouse.objects.create(
            store=self.store,
            name="Almacén concurrente",
        )
        StockByWarehouse.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=Decimal("1.000"),
        )
        self.document_type, _ = DocumentType.objects.get_or_create(
            code="NV",
            defaults={"name": "Nota de venta", "category": "INTERNAL"},
        )
        self.series = DocumentSeries.objects.create(
            company=self.company,
            store=self.store,
            document_type=self.document_type,
            series="NC01",
        )
        self.cash = MeansOfPayment.objects.create(
            company=self.company,
            name="Efectivo concurrente",
            kind=MeansOfPayment.Kind.CASH,
        )
        self.sessions = []
        for index in range(2):
            register = PosRegister.objects.create(
                company=self.company,
                store=self.store,
                code=f"PC-{index + 1}",
                name=f"Caja concurrente {index + 1}",
                default_warehouse=self.warehouse,
                default_customer=self.customer,
                default_document_type=self.document_type,
                ticket_series=f"C{index + 1}",
            )
            self.sessions.append(open_cash_session(
                register_id=register.pk,
                opened_by=self.user,
            ))

    def test_two_registers_cannot_sell_the_same_last_stock_unit(self):
        barrier = Barrier(2)

        def sell(session_id):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                transaction, _ = checkout_pos_sale(
                    company_id=self.company.pk,
                    store_id=self.store.pk,
                    register_id=next(
                        session.register_id
                        for session in self.sessions
                        if session.pk == session_id
                    ),
                    cash_session_id=session_id,
                    idempotency_key=uuid.uuid4(),
                    document_type_code="NV",
                    series_id=self.series.pk,
                    customer_id=self.customer.pk,
                    warehouse_id=self.warehouse.pk,
                    currency="PEN",
                    line_items=[{
                        "product_id": self.product.pk,
                        "unit_id": self.unit.pk,
                        "quantity": Decimal("1.000"),
                        "discount_amount": Decimal("0.00"),
                        "tax_type": "10",
                        "igv_rate": Decimal("18.00"),
                    }],
                    payment_items=[{
                        "means_of_payment_id": self.cash.pk,
                        "amount": Decimal("10.00"),
                        "received_amount": Decimal("10.00"),
                        "change_amount": Decimal("0.00"),
                    }],
                    cashier=User.objects.get(pk=self.user.pk),
                )
                return "OK", str(transaction.pk)
            except PosDomainError as exc:
                return exc.code, str(exc)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(sell, [session.pk for session in self.sessions]))

        self.assertEqual(sorted(code for code, _ in results), ["INVALID_POS_SALE", "OK"])
        stock = StockByWarehouse.objects.get(
            product=self.product,
            warehouse=self.warehouse,
        )
        self.assertEqual(stock.quantity, Decimal("0.000"))
        self.assertEqual(PosTransaction.objects.count(), 1)
        self.assertEqual(SalesDocument.objects.count(), 1)
        self.assertEqual(
            Movement.objects.filter(origin=MovementOrigin.SALE).count(),
            1,
        )
        self.series.refresh_from_db()
        self.assertEqual(self.series.current_number, 1)
