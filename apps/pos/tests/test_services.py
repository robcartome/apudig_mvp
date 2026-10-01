import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.core.models import AuditLog
from apps.inventory.models import Product, Unit, Warehouse
from apps.partners.models import Customer, DocumentType
from apps.sales.models import DocumentSeries, MeansOfPayment
from apps.sales.services import create_sales_document_draft, issue_sales_document

from apps.pos import selectors
from apps.pos.models import (
    CashDenominationCount,
    CashMovement,
    CashSafeMovement,
    CashSession,
    CashTenderDeclaration,
    PosRegister,
    PosTransaction,
    SalesDocumentSource,
)
from apps.pos.services import (
    PosDomainError,
    close_cash_session,
    complete_pos_transaction,
    link_tickets_to_consolidated_invoice,
    open_cash_session,
    request_consolidated_invoice,
    register_cash_movement,
    register_sales_payment,
    start_pos_transaction,
    void_pos_transaction,
)


User = get_user_model()


class PosServiceTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Ferreteria POS", ruc="20123456789")
        self.store = Store.objects.create(company=self.company, name="Tienda principal")
        self.other_store = Store.objects.create(company=self.company, name="Tienda secundaria")
        self.user = User.objects.create_user(email="cajero@example.com", password="test")
        self.customer = Customer.objects.create(
            company=self.company,
            document_type="6",
            document_number="20654321987",
            legal_name="Cliente Ferretero SAC",
        )
        self.unit = Unit.objects.create(code="NIU", name="Unidad")
        self.product = Product.objects.create(
            company=self.company,
            name="Taladro",
            sku="TAL-001",
            unit=self.unit,
            price_sale=Decimal("100.00"),
            tracks_inventory=False,
        )
        self.warehouse = Warehouse.objects.create(
            store=self.store,
            name="Almacen principal",
            is_default=True,
        )
        self.nv_type = DocumentType.objects.create(
            code="NV",
            name="Nota de Venta",
            category="INTERNAL",
        )
        self.invoice_type = DocumentType.objects.create(
            code="01",
            name="Factura",
            category="BILLING",
            is_sunat=True,
            sunat_code="01",
        )
        self.nv_series = DocumentSeries.objects.create(
            company=self.company,
            store=self.store,
            document_type=self.nv_type,
            series="NV01",
        )
        self.invoice_series = DocumentSeries.objects.create(
            company=self.company,
            store=self.store,
            document_type=self.invoice_type,
            series="F001",
        )
        self.cash = MeansOfPayment.objects.create(
            company=self.company,
            name="Efectivo",
            kind=MeansOfPayment.Kind.CASH,
        )
        self.wallet = MeansOfPayment.objects.create(
            company=self.company,
            name="Yape",
            kind=MeansOfPayment.Kind.DIGITAL_WALLET,
            requires_reference=True,
        )
        self.register = PosRegister.objects.create(
            company=self.company,
            store=self.store,
            code="POS-01",
            name="Caja mostrador",
            default_warehouse=self.warehouse,
            default_customer=self.customer,
            default_document_type=self.nv_type,
            ticket_series="T01",
        )

    def _line(self, quantity="1"):
        return {
            "product": self.product,
            "description": self.product.name,
            "quantity": Decimal(quantity),
            "unit_price": Decimal("100.00"),
            "unit_code": "NIU",
            "discount_amount": Decimal("0.00"),
            "tax_type": "10",
            "igv_rate": Decimal("18.00"),
        }

    def _document(self, *, document_type=None, series=None, quantity="1", issue=True):
        document_type = document_type or self.nv_type
        series = series or self.nv_series
        document = create_sales_document_draft(
            store_id=str(self.store.pk),
            customer=self.customer,
            document_type=document_type,
            series=series,
            lines=[self._line(quantity)],
            created_by=self.user,
            issue_date=timezone.now(),
            currency="PEN",
            register_inventory_movement=False,
        )
        if issue:
            document = issue_sales_document(document.pk, issued_by=self.user)
        return document

    def _session(self, opening="100.00"):
        return open_cash_session(
            register_id=self.register.pk,
            opened_by=self.user,
            opening_total=opening,
        )

    def _completed_ticket(self, session, *, means=None, reference=""):
        document = self._document()
        pos_transaction, _ = start_pos_transaction(
            cash_session_id=session.pk,
            sales_document_id=document.pk,
            idempotency_key=uuid.uuid4(),
            cashier=self.user,
        )
        register_sales_payment(
            sales_document_id=document.pk,
            cash_session_id=session.pk,
            means_of_payment_id=(means or self.cash).pk,
            amount=document.total,
            received_amount=document.total,
            operation_reference=reference,
            created_by=self.user,
        )
        complete_pos_transaction(pos_transaction.pk, completed_by=self.user)
        document.refresh_from_db()
        return document, pos_transaction

    def test_open_cash_session_persists_denomination_count(self):
        session = open_cash_session(
            register_id=self.register.pk,
            opened_by=self.user,
            opening_total="100.00",
            denominations=[{"denomination": "50", "quantity": 2}],
        )

        count = session.denomination_counts.get(phase=CashDenominationCount.Phase.OPENING)
        self.assertEqual(count.total, Decimal("100.00"))
        self.assertEqual(session.status, CashSession.Status.OPEN)

    def test_only_one_open_session_is_allowed_per_register(self):
        self._session()

        with self.assertRaises(PosDomainError) as error:
            self._session()

        self.assertEqual(error.exception.code, "CASH_SESSION_ALREADY_OPEN")

    def test_session_number_increments_per_register(self):
        first = self._session(opening="0.00")
        close_cash_session(
            cash_session_id=first.pk,
            closed_by=self.user,
            counted_cash_total="0.00",
        )

        second = open_cash_session(
            register_id=self.register.pk,
            opened_by=self.user,
            opening_total="0.00",
            currency="USD",
        )

        self.assertEqual(first.session_number, 1)
        self.assertEqual(second.session_number, 2)
        self.assertEqual(second.currency, "USD")

    def test_payment_currency_must_match_cash_session(self):
        session = open_cash_session(
            register_id=self.register.pk,
            opened_by=self.user,
            opening_total="0.00",
            currency="USD",
        )
        document = self._document()

        with self.assertRaises(PosDomainError) as error:
            start_pos_transaction(
                cash_session_id=session.pk,
                sales_document_id=document.pk,
                idempotency_key=uuid.uuid4(),
                cashier=self.user,
            )

        self.assertEqual(error.exception.code, "CASH_SESSION_CURRENCY_MISMATCH")

    def test_register_rejects_store_from_another_company(self):
        other_company = Company.objects.create(name="Otra empresa", ruc="20999999991")
        foreign_store = Store.objects.create(company=other_company, name="Sucursal ajena")
        invalid_register = PosRegister(
            company=self.company,
            store=foreign_store,
            code="INVALID",
            name="Caja invalida",
        )

        with self.assertRaises(ValidationError):
            invalid_register.full_clean()

    def test_opening_denomination_mismatch_rolls_back_session(self):
        with self.assertRaises(PosDomainError) as error:
            open_cash_session(
                register_id=self.register.pk,
                opened_by=self.user,
                opening_total="100.00",
                denominations=[{"denomination": "20", "quantity": 2}],
            )

        self.assertEqual(error.exception.code, "OPENING_COUNT_MISMATCH")
        self.assertFalse(CashSession.objects.exists())

    def test_start_transaction_is_idempotent_and_assigns_one_ticket_number(self):
        session = self._session()
        document = self._document()
        key = uuid.uuid4()

        first, created = start_pos_transaction(
            cash_session_id=session.pk,
            sales_document_id=document.pk,
            idempotency_key=key,
            cashier=self.user,
        )
        repeated, repeated_created = start_pos_transaction(
            cash_session_id=session.pk,
            sales_document_id=document.pk,
            idempotency_key=key,
            cashier=self.user,
        )

        self.assertTrue(created)
        self.assertFalse(repeated_created)
        self.assertEqual(first.pk, repeated.pk)
        self.assertEqual(first.ticket_code, "T01-00000001")
        self.register.refresh_from_db()
        self.assertEqual(self.register.current_ticket_number, 1)

    def test_transaction_rejects_document_from_another_store(self):
        other_series = DocumentSeries.objects.create(
            company=self.company,
            store=self.other_store,
            document_type=self.nv_type,
            series="NV02",
        )
        document = create_sales_document_draft(
            store_id=str(self.other_store.pk),
            customer=self.customer,
            document_type=self.nv_type,
            series=other_series,
            lines=[self._line()],
            created_by=self.user,
            issue_date=timezone.now(),
            currency="PEN",
            register_inventory_movement=False,
        )
        session = self._session()

        with self.assertRaises(PosDomainError) as error:
            start_pos_transaction(
                cash_session_id=session.pk,
                sales_document_id=document.pk,
                idempotency_key=uuid.uuid4(),
                cashier=self.user,
            )

        self.assertEqual(error.exception.code, "STORE_MISMATCH")

    def test_mixed_payments_can_complete_exact_total(self):
        session = self._session()
        document = self._document()
        pos_transaction, _ = start_pos_transaction(
            cash_session_id=session.pk,
            sales_document_id=document.pk,
            idempotency_key=uuid.uuid4(),
            cashier=self.user,
        )

        register_sales_payment(
            sales_document_id=document.pk,
            cash_session_id=session.pk,
            means_of_payment_id=self.cash.pk,
            amount="50.00",
            received_amount="70.00",
            change_amount="20.00",
            created_by=self.user,
        )
        register_sales_payment(
            sales_document_id=document.pk,
            cash_session_id=session.pk,
            means_of_payment_id=self.wallet.pk,
            amount="68.00",
            operation_reference="YAPE-001",
            created_by=self.user,
        )
        completed = complete_pos_transaction(pos_transaction.pk, completed_by=self.user)

        self.assertEqual(completed.status, PosTransaction.Status.COMPLETED)
        self.assertEqual(document.pos_payments.count(), 2)

    def test_payment_reference_is_optional_for_configured_tender(self):
        session = self._session()
        document = self._document()

        payment = register_sales_payment(
            sales_document_id=document.pk,
            cash_session_id=session.pk,
            means_of_payment_id=self.wallet.pk,
            amount=document.total,
            created_by=self.user,
        )

        self.assertEqual(payment.operation_reference, "")

    def test_payment_cannot_exceed_document_total(self):
        session = self._session()
        document = self._document()

        with self.assertRaises(PosDomainError) as error:
            register_sales_payment(
                sales_document_id=document.pk,
                cash_session_id=session.pk,
                means_of_payment_id=self.cash.pk,
                amount="119.00",
                received_amount="119.00",
                created_by=self.user,
            )

        self.assertEqual(error.exception.code, "PAYMENT_EXCEEDS_TOTAL")

    def test_multiple_completed_tickets_can_be_consolidated_once(self):
        session = self._session()
        first, first_transaction = self._completed_ticket(session)
        second, second_transaction = self._completed_ticket(session)
        invoice = self._document(
            document_type=self.invoice_type,
            series=self.invoice_series,
            quantity="2",
        )

        links = link_tickets_to_consolidated_invoice(
            source_document_ids=[first.pk, second.pk],
            target_document_id=invoice.pk,
            created_by=self.user,
        )

        self.assertEqual(len(links), 2)
        self.assertEqual(SalesDocumentSource.objects.filter(target_document=invoice).count(), 2)
        first_transaction.refresh_from_db()
        second_transaction.refresh_from_db()
        self.assertEqual(first_transaction.billing_status, PosTransaction.BillingStatus.INVOICED)
        self.assertEqual(second_transaction.billing_status, PosTransaction.BillingStatus.INVOICED)

        with self.assertRaises(PosDomainError) as error:
            link_tickets_to_consolidated_invoice(
                source_document_ids=[first.pk],
                target_document_id=invoice.pk,
                created_by=self.user,
            )
        self.assertEqual(error.exception.code, "CONSOLIDATED_TOTAL_MISMATCH")

        duplicate_target = self._document(
            document_type=self.invoice_type,
            series=self.invoice_series,
        )
        with self.assertRaises(PosDomainError) as error:
            link_tickets_to_consolidated_invoice(
                source_document_ids=[first.pk],
                target_document_id=duplicate_target.pk,
                created_by=self.user,
            )
        self.assertEqual(error.exception.code, "INVALID_INVOICE_SOURCE")

    def test_consolidation_rejects_total_mismatch(self):
        session = self._session()
        ticket, _ = self._completed_ticket(session)
        invoice = self._document(
            document_type=self.invoice_type,
            series=self.invoice_series,
            quantity="2",
        )

        with self.assertRaises(PosDomainError) as error:
            link_tickets_to_consolidated_invoice(
                source_document_ids=[ticket.pk],
                target_document_id=invoice.pk,
                created_by=self.user,
            )

        self.assertEqual(error.exception.code, "CONSOLIDATED_TOTAL_MISMATCH")

    def test_close_cash_session_calculates_expected_cash_and_tender_totals(self):
        session = self._session(opening="100.00")
        self._completed_ticket(session)
        register_cash_movement(
            cash_session_id=session.pk,
            movement_type=CashMovement.MovementType.PAY_IN,
            amount="10.00",
            description="Cambio adicional",
            created_by=self.user,
        )
        register_cash_movement(
            cash_session_id=session.pk,
            movement_type=CashMovement.MovementType.PAY_OUT,
            amount="8.00",
            description="Compra menor",
            created_by=self.user,
        )

        closed = close_cash_session(
            cash_session_id=session.pk,
            closed_by=self.user,
            counted_cash_total="220.00",
            denominations=[
                {"denomination": "100.00", "quantity": 2},
                {"denomination": "20.00", "quantity": 1},
            ],
            next_opening_total="100.00",
            tender_counts=[
                {"means_of_payment_id": self.cash.pk, "counted_amount": "118.00"},
            ],
        )

        self.assertEqual(closed.expected_cash_total, Decimal("220.00"))
        self.assertEqual(closed.cash_difference, Decimal("0.00"))
        self.assertEqual(closed.next_opening_total, Decimal("100.00"))
        self.assertEqual(closed.safe_deposit_total, Decimal("120.00"))
        self.assertEqual(closed.bank_deposit_total, Decimal("0.00"))
        safe_movement = CashSafeMovement.objects.get(cash_session=closed)
        self.assertEqual(safe_movement.amount, Decimal("120.00"))
        self.assertEqual(safe_movement.direction, CashSafeMovement.Direction.IN)
        declaration = CashTenderDeclaration.objects.get(
            cash_session=session,
            means_of_payment=self.cash,
        )
        self.assertEqual(declaration.expected_amount, Decimal("118.00"))
        self.assertEqual(declaration.difference, Decimal("0.00"))
        audit = AuditLog.objects.get(entity="CashSession", entity_id=str(session.pk), action="CLOSE")
        self.assertEqual(audit.meta_data["opening_total"], "100.00")
        self.assertEqual(audit.meta_data["cash_payments"], "118.00")
        self.assertEqual(audit.meta_data["cash_in"], "10.00")
        self.assertEqual(audit.meta_data["cash_out"], "8.00")

    def test_close_requires_complete_cash_custody_allocation(self):
        session = self._session(opening="100.00")

        with self.assertRaises(PosDomainError) as error:
            close_cash_session(
                cash_session_id=session.pk,
                closed_by=self.user,
                counted_cash_total="100.00",
                next_opening_total="20.00",
                safe_deposit_total="50.00",
                bank_deposit_total="10.00",
                bank_deposit_destination="BCP",
            )

        self.assertEqual(error.exception.code, "CASH_ALLOCATION_MISMATCH")

    def test_cash_session_summary_separates_cash_tenders_and_movements(self):
        session = self._session(opening="100.00")
        self._completed_ticket(session)
        self._completed_ticket(session, means=self.wallet, reference="YAPE-001")
        register_cash_movement(
            cash_session_id=session.pk,
            movement_type=CashMovement.MovementType.PAY_IN,
            amount="10.00",
            description="Fondo adicional",
            created_by=self.user,
        )
        register_cash_movement(
            cash_session_id=session.pk,
            movement_type=CashMovement.MovementType.WITHDRAWAL,
            amount="8.00",
            description="Retiro preventivo",
            created_by=self.user,
            authorized_by=self.user,
        )

        summary = selectors.get_cash_session_summary(session)

        self.assertEqual(summary["payment_total"], Decimal("236.00"))
        self.assertEqual(summary["cash_sales"], Decimal("118.00"))
        self.assertEqual(summary["non_cash_sales"], Decimal("118.00"))
        self.assertEqual(summary["expected_cash_total"], Decimal("220.00"))
        self.assertEqual(summary["transactions"]["completed"], 2)
        self.assertTrue(summary["can_close"])

    def test_daily_pos_totals_combine_multiple_sessions_same_day(self):
        first = self._session(opening="0.00")
        self._completed_ticket(first)
        self._completed_ticket(first)
        close_cash_session(
            cash_session_id=first.pk,
            closed_by=self.user,
            counted_cash_total="236.00",
        )
        second = self._session(opening="0.00")
        self._completed_ticket(second)

        totals = selectors.get_daily_pos_sales_totals(
            company_id=self.company.pk,
            store_id=self.store.pk,
            business_date=timezone.localdate(),
        )

        self.assertEqual(len(totals), 1)
        self.assertEqual(totals[0]["sessions"], 2)
        self.assertEqual(totals[0]["sales_count"], 3)
        self.assertEqual(totals[0]["sales_total"], Decimal("354.00"))

    def test_close_requires_non_cash_tender_reconciliation(self):
        session = self._session(opening="0.00")
        self._completed_ticket(session, means=self.wallet, reference="YAPE-002")

        with self.assertRaises(PosDomainError) as error:
            close_cash_session(
                cash_session_id=session.pk,
                closed_by=self.user,
                counted_cash_total="0.00",
            )

        self.assertEqual(error.exception.code, "TENDER_DECLARATION_REQUIRED")

    def test_non_cash_tender_difference_requires_authorization(self):
        session = self._session(opening="0.00")
        self._completed_ticket(session, means=self.wallet, reference="YAPE-003")
        tender_counts = [{
            "means_of_payment_id": self.wallet.pk,
            "counted_amount": "100.00",
        }]

        with self.assertRaises(PosDomainError) as error:
            close_cash_session(
                cash_session_id=session.pk,
                closed_by=self.user,
                counted_cash_total="0.00",
                tender_counts=tender_counts,
            )
        self.assertEqual(
            error.exception.code,
            "TENDER_DIFFERENCE_AUTHORIZATION_REQUIRED",
        )

        closed = close_cash_session(
            cash_session_id=session.pk,
            closed_by=self.user,
            counted_cash_total="0.00",
            tender_counts=tender_counts,
            difference_authorized_by=self.user,
            note="Diferencia de Yape verificada por supervisor",
        )
        self.assertEqual(closed.difference_authorized_by, self.user)

    def test_close_is_blocked_while_invoice_request_is_pending(self):
        session = self._session()
        ticket, pos_transaction = self._completed_ticket(session)
        requested = request_consolidated_invoice(
            source_document_ids=[ticket.pk],
            requested_by=self.user,
        )

        self.assertEqual(requested[0].pk, pos_transaction.pk)
        self.assertEqual(
            requested[0].billing_status,
            PosTransaction.BillingStatus.INVOICE_REQUESTED,
        )

        with self.assertRaises(PosDomainError) as error:
            close_cash_session(
                cash_session_id=session.pk,
                closed_by=self.user,
                counted_cash_total="218.00",
            )

        self.assertEqual(error.exception.code, "CLOSE_HAS_PENDING_INVOICES")

    def test_cash_difference_requires_explicit_authorization(self):
        session = self._session(opening="100.00")

        with self.assertRaises(PosDomainError) as error:
            close_cash_session(
                cash_session_id=session.pk,
                closed_by=self.user,
                counted_cash_total="90.00",
            )
        self.assertEqual(error.exception.code, "CASH_DIFFERENCE_AUTHORIZATION_REQUIRED")

        closed = close_cash_session(
            cash_session_id=session.pk,
            closed_by=self.user,
            counted_cash_total="90.00",
            difference_authorized_by=self.user,
            note="Faltante informado durante el arqueo",
        )
        self.assertEqual(closed.cash_difference, Decimal("-10.00"))
        self.assertEqual(closed.difference_authorized_by, self.user)

    def test_withdrawal_requires_authorization(self):
        session = self._session(opening="100.00")

        with self.assertRaises(PosDomainError) as error:
            register_cash_movement(
                cash_session_id=session.pk,
                movement_type=CashMovement.MovementType.WITHDRAWAL,
                amount="20.00",
                description="Retiro a boveda",
                created_by=self.user,
            )

        self.assertEqual(error.exception.code, "CASH_MOVEMENT_AUTHORIZATION_REQUIRED")
        self.assertFalse(session.cash_movements.exists())

        movement = register_cash_movement(
            cash_session_id=session.pk,
            movement_type=CashMovement.MovementType.WITHDRAWAL,
            amount="20.00",
            description="Deposito en caja fuerte",
            reason_code="SAFE_WITHDRAWAL",
            created_by=self.user,
            authorized_by=self.user,
        )
        self.assertEqual(movement.drawer_cash_after, Decimal("80.00"))

    def test_authorized_difference_requires_closing_reason(self):
        session = self._session(opening="100.00")

        with self.assertRaises(PosDomainError) as error:
            close_cash_session(
                cash_session_id=session.pk,
                closed_by=self.user,
                counted_cash_total="90.00",
                difference_authorized_by=self.user,
            )

        self.assertEqual(error.exception.code, "CASH_DIFFERENCE_REASON_REQUIRED")
        session.refresh_from_db()
        self.assertEqual(session.status, CashSession.Status.OPEN)

    def test_void_sale_cancels_payments_and_removes_it_from_expected_cash(self):
        session = self._session(opening="100.00")
        document, pos_transaction = self._completed_ticket(session)

        cancelled = void_pos_transaction(
            pos_transaction_id=pos_transaction.pk,
            reason="Error de digitacion",
            voided_by=self.user,
        )

        document.refresh_from_db()
        self.assertEqual(cancelled.status, PosTransaction.Status.CANCELLED)
        self.assertEqual(document.status, "VOIDED")
        self.assertEqual(document.pos_payments.get().status, "CANCELLED")
        closed = close_cash_session(
            cash_session_id=session.pk,
            closed_by=self.user,
            counted_cash_total="100.00",
        )
        self.assertEqual(closed.expected_cash_total, Decimal("100.00"))
