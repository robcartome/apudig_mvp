from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.partners.models import DocumentType
from apps.pos.models import CashSession, PosRegister, PosTransaction, SalesPayment
from apps.pos.selectors import calculate_cash_session_totals
from apps.pos.services import register_credit_collection, register_sales_payment
from apps.sales.models import DocumentSeries, MeansOfPayment, PaymentMethod, SalesDocument
from apps.sales.forms import SalesDocumentHeaderForm
from apps.sales.payment_services import document_payment_summary, register_document_collection
from apps.sales.selectors import with_document_payments
from apps.treasury.models import Bank, BankAccount, BankMovement
from apps.users.models import Permission, Role, RolePermission, UserRole, UserStore


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class SalesCollectionTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Cobros", ruc="20123456789")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.user = get_user_model().objects.create_superuser(
            email="collections@example.com", password="test",
        )
        self.credit = PaymentMethod.objects.create(
            company=self.company, name="Crédito 30 días", is_credit=True,
            immediate_payment=False, credit_days=30,
        )
        self.cash = MeansOfPayment.objects.create(
            company=self.company, name="Efectivo", kind=MeansOfPayment.Kind.CASH,
        )
        self.wallet = MeansOfPayment.objects.create(
            company=self.company, name="Yape", kind=MeansOfPayment.Kind.DIGITAL_WALLET,
        )
        self.register = PosRegister.objects.create(
            company=self.company, store=self.store, code="CAJA1", name="Caja principal",
        )
        self.session = CashSession.objects.create(
            company=self.company, store=self.store, register=self.register,
            session_number=1, opened_by=self.user, opening_total=Decimal("0.00"),
        )
        doc_type, _ = DocumentType.objects.get_or_create(
            code="NV", defaults={"name": "Nota de venta", "category": "INTERNAL"},
        )
        self.document = SalesDocument.objects.create(
            store=self.store, document_type=doc_type, status="ISSUED",
            customer_document_type="1", customer_document_number="12345678",
            customer_legal_name="Cliente crédito", issue_date=timezone.now(),
            payment_method=self.credit, series_code="NV01", number="00000001",
            total=Decimal("118.00"), due_date=timezone.localdate(),
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()
        self.url = reverse("sales:payment_create", args=[self.document.pk])

    def _payload(self, amount="40.00", **overrides):
        data = {
            "cash_session": str(self.session.pk), "means_of_payment": str(self.cash.pk),
            "amount": amount, "operation_reference": "OP-123", "idempotency_key": str(uuid4()),
        }
        data.update(overrides)
        return data

    def _post(self, data):
        return self.client.post(self.url, data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    def _pos_transaction(self):
        return PosTransaction.objects.create(
            company=self.company, store=self.store, register=self.register,
            cash_session=self.session, sales_document=self.document, cashier=self.user,
            status=PosTransaction.Status.COMPLETED, payment_condition="CREDIT",
            completed_at=timezone.now(), ticket_number=1, ticket_code="T01-1",
            idempotency_key=uuid4(),
        )

    def test_partial_and_full_collections_share_cash_ledger_and_list(self):
        response = self.client.get(self.url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertContains(response, 'name="idempotency_key"')
        self.assertContains(response, 'value="118.00"')
        self.assertContains(response, "Caja principal")
        first = self._post(self._payload())
        self.assertEqual(first.status_code, 200)
        payment = self.document.pos_payments.get()
        self.assertEqual(payment.purpose, SalesPayment.Purpose.CREDIT_COLLECTION)
        self.assertEqual(payment.cash_session, self.session)
        self.assertEqual(payment.created_by, self.user)
        self.assertEqual(calculate_cash_session_totals(self.session)["cash_payments"], Decimal("40"))
        summary = document_payment_summary(self.document)
        self.assertEqual(summary["balance"], Decimal("78"))
        self.assertEqual(summary["status"], "PARTIAL")
        response = self.client.get(reverse("sales:document_list"))
        row = response.context["page_obj"][0]
        self.assertEqual(row.payment_summary["balance"], Decimal("78"))
        self.assertContains(response, "Registrar cobranza")
        self.assertContains(response, "Efectivo")
        self.assertContains(response, timezone.localtime(payment.paid_at).strftime("%d/%m/%Y %H:%M"))
        self.assertEqual(self._post(self._payload("78", means_of_payment=str(self.wallet.pk))).status_code, 200)
        summary = document_payment_summary(self.document)
        self.assertEqual(summary["paid"], Decimal("118"))
        self.assertEqual(summary["balance"], 0)
        self.assertEqual(summary["status"], "PAID")
        self.assertEqual(summary["means"], ["Efectivo", "Yape"])
        response = self.client.get(reverse("sales:document_list"))
        self.assertNotContains(response, 'class="btn btn-sm btn-outline-primary js-sales-payment"')

    def test_pos_collection_appears_in_sales_history_and_sales_collection_updates_pos(self):
        pos = self._pos_transaction()
        payment = register_credit_collection(
            sales_document_id=self.document.pk, cash_session_id=self.session.pk,
            means_of_payment_id=self.wallet.pk, amount="40", operation_reference="YAPE-456",
            created_by=self.user, idempotency_key=uuid4(),
        )
        response = self.client.get(reverse("sales:document_list"))
        self.assertEqual(response.context["page_obj"][0].payment_summary["paid"], Decimal("40"))
        for view in ("sales:document_preview", "sales:document_detail"):
            response = self.client.get(reverse(view, args=[self.document.pk]))
            self.assertContains(response, "YAPE-456")
            self.assertContains(response, "Yape")
            self.assertContains(response, timezone.localtime(payment.paid_at).strftime("%d/%m/%Y %H:%M"))
        self.assertEqual(self._post(self._payload("78")).status_code, 200)
        pos.refresh_from_db()
        self.assertEqual(pos.payment_status, PosTransaction.PaymentStatus.PAID)

    def test_retry_does_not_duplicate_even_after_full_payment(self):
        data = self._payload("118")
        self.assertEqual(self._post(data).status_code, 200)
        self.assertEqual(self._post(data).status_code, 200)
        self.assertEqual(self.document.pos_payments.count(), 1)

    def test_sales_collection_can_use_a_later_session_than_original_pos_sale(self):
        pos = self._pos_transaction()
        self.session.status = CashSession.Status.CLOSED
        self.session.save(update_fields=["status"])
        later_session = CashSession.objects.create(
            company=self.company, store=self.store, register=self.register,
            session_number=2, opened_by=self.user,
        )
        self.assertEqual(self._post(self._payload("118", cash_session=str(later_session.pk))).status_code, 200)
        self.assertEqual(self.document.pos_payments.get().cash_session, later_session)
        pos.refresh_from_db()
        self.assertEqual(pos.payment_status, PosTransaction.PaymentStatus.PAID)
        response = self.client.get(f"/api/v1/pos/sessions/{later_session.pk}/summary/")
        self.assertEqual(response.status_code, 200)
        summary = response.json()
        self.assertEqual(Decimal(summary["collection_total"]), Decimal("118"))
        self.assertEqual(Decimal(summary["sales_total"]), Decimal("0"))
        self.assertEqual(summary["daily_summary"], [])
        self.assertEqual(Decimal(summary["expected_cash_total"]), Decimal("118"))
        self.assertEqual(summary["collections"][0]["document"], "NV01-00000001")
        self.assertEqual(summary["collections"][0]["means"], "Efectivo")
        self.assertEqual(summary["payment_breakdown"][0]["purpose"], "CREDIT_COLLECTION")

    def test_closing_summary_separates_cash_and_wallet_collections_and_ignores_cancelled(self):
        self.assertEqual(self._post(self._payload("20")).status_code, 200)
        self.assertEqual(self._post(self._payload("30", means_of_payment=str(self.wallet.pk))).status_code, 200)
        self.assertEqual(self._post(self._payload("10")).status_code, 200)
        cancelled = self.document.pos_payments.order_by("-created_at").first()
        cancelled.status = SalesPayment.Status.CANCELLED
        cancelled.save(update_fields=["status"])
        response = self.client.get(f"/api/v1/pos/sessions/{self.session.pk}/summary/")
        self.assertEqual(response.status_code, 200)
        summary = response.json()
        self.assertEqual(Decimal(summary["collection_total"]), Decimal("50"))
        self.assertEqual(Decimal(summary["expected_cash_total"]), Decimal("20"))
        self.assertEqual(len(summary["collections"]), 2)
        self.assertEqual({row["means"] for row in summary["payment_breakdown"]}, {"Efectivo", "Yape"})

    def test_overpayment_and_nonpositive_amounts_are_rejected(self):
        for amount in ("119", "0", "-1", "NaN"):
            with self.subTest(amount=amount):
                self.assertEqual(self._post(self._payload(amount)).status_code, 400)
        self.assertFalse(self.document.pos_payments.exists())

    def test_ineligible_documents_cannot_be_collected(self):
        for status in ("DRAFT", "VOIDED", "CANCELLED", "SUNAT_REJECTED"):
            self.document.status = status
            self.document.save(update_fields=["status"])
            with self.subTest(status=status):
                self.assertEqual(self._post(self._payload()).status_code, 400)
        self.document.status = "ISSUED"
        self.document.payment_method = None
        self.document.save(update_fields=["status", "payment_method"])
        self.assertEqual(self._post(self._payload()).status_code, 200)
        self.assertEqual(self.document.pos_payments.count(), 1)

    def test_cancelled_and_refunded_payments_do_not_reduce_balance(self):
        for status in (SalesPayment.Status.CANCELLED, SalesPayment.Status.REFUNDED):
            self.assertEqual(self._post(self._payload()).status_code, 200)
            self.document.pos_payments.filter(status="REGISTERED").update(status=status)
        summary = document_payment_summary(self.document)
        self.assertEqual(summary["balance"], Decimal("118"))
        self.assertIsNone(summary["last_payment"])
        self.assertEqual(len(summary["payments"]), 2)

    def test_other_company_or_store_cannot_supply_document_session_or_means(self):
        other_company = Company.objects.create(name="Otra empresa", ruc="20987654321")
        other_store = Store.objects.create(company=other_company, name="Otra sucursal")
        other_means = MeansOfPayment.objects.create(company=other_company, name="Efectivo")
        self.assertEqual(self._post(self._payload(means_of_payment=str(other_means.pk))).status_code, 400)
        other_register = PosRegister.objects.create(
            company=other_company, store=other_store, code="OTRA", name="Otra caja",
        )
        other_session = CashSession.objects.create(
            company=other_company, store=other_store, register=other_register, session_number=1,
        )
        self.assertEqual(self._post(self._payload(cash_session=str(other_session.pk))).status_code, 400)
        self.document.store = other_store
        self.document.save(update_fields=["store"])
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self._post(self._payload()).status_code, 404)
        self.assertFalse(self.document.pos_payments.exists())

    def test_closed_session_or_wrong_currency_is_rejected(self):
        self.session.status = CashSession.Status.CLOSED
        self.session.save(update_fields=["status"])
        response = self.client.get(self.url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertContains(response, "Abre una sesión de caja en PEN")
        self.assertEqual(self._post(self._payload()).status_code, 400)
        self.session.status = CashSession.Status.OPEN
        self.session.currency = "USD"
        self.session.save(update_fields=["status", "currency"])
        self.assertEqual(self._post(self._payload()).status_code, 400)
        self.assertFalse(self.document.pos_payments.exists())

    def test_collection_requires_both_sales_and_collection_permissions(self):
        self.user.is_superuser = False
        self.user.save(update_fields=["is_superuser"])
        UserStore.objects.create(user=self.user, store=self.store, role="SELLER")
        role = Role.objects.create(name="COLLECTOR_TEST")
        UserRole.objects.create(user=self.user, company=self.company, role=role)
        for action, module in (("read", "sales.documents"), ("manage", "sales.documents"), ("manage", "pos.collections")):
            permission, _ = Permission.objects.get_or_create(
                code=f"{action}.{module}", defaults={"action_name": action, "module": module},
            )
            if action == "read":
                RolePermission.objects.create(role=role, permission=permission)
        self.assertEqual(self._post(self._payload()).status_code, 403)
        RolePermission.objects.create(role=role, permission=Permission.objects.get(code="manage.sales.documents"))
        self.assertEqual(self._post(self._payload()).status_code, 403)
        RolePermission.objects.create(role=role, permission=Permission.objects.get(code="manage.pos.collections"))
        self.assertEqual(self._post(self._payload()).status_code, 200)

    def test_fresh_payment_cannot_collect_stale_balance(self):
        data = self._payload("78")
        self.assertEqual(self._post(self._payload("80")).status_code, 200)
        self.assertEqual(self._post(data).status_code, 400)
        self.assertEqual(document_payment_summary(self.document)["balance"], Decimal("38"))

    def test_service_rejects_foreign_scope_even_without_view(self):
        with self.assertRaises(SalesDocument.DoesNotExist):
            register_document_collection(
                document_id=self.document.pk, company_id=uuid4(), store_id=self.store.pk,
                cash_session_id=self.session.pk, means_of_payment_id=self.cash.pk,
                amount="40", idempotency_key=uuid4(), created_by=self.user,
            )

    def test_collection_with_linked_account_records_one_bank_receipt(self):
        bank = Bank.objects.create(company=self.company, name="Banco de prueba")
        account = BankAccount.objects.create(
            company=self.company, bank=bank, name="Cuenta cobros", account_number="123456789",
            opening_balance_date=timezone.localdate(),
        )
        self.wallet.bank_account = account
        self.wallet.save(update_fields=["bank_account"])
        data = self._payload(means_of_payment=str(self.wallet.pk))
        self.assertEqual(self._post(data).status_code, 200)
        self.assertEqual(self._post(data).status_code, 200)
        payment = self.document.pos_payments.get()
        movement = BankMovement.objects.get(account=account)
        self.assertEqual(movement.amount, Decimal("40"))
        self.assertEqual(movement.direction, BankMovement.Direction.IN)
        self.assertEqual(movement.source_id, str(payment.pk))
        self.assertEqual(movement.source_type, "POS_SALE_PAYMENT")

    def test_prefetched_summaries_do_not_query_for_each_document_or_payment(self):
        self.assertEqual(self._post(self._payload()).status_code, 200)
        with self.assertNumQueries(2):
            documents = list(with_document_payments(SalesDocument.objects.filter(store=self.store)))
            summaries = [document_payment_summary(document) for document in documents]
        self.assertEqual(summaries[0]["balance"], Decimal("78"))

    def test_document_summary_splits_means_without_duplicating_sale_total(self):
        self._pos_transaction()
        for means, amount in ((self.cash, "40"), (self.wallet, "30")):
            register_sales_payment(
                sales_document_id=self.document.pk, cash_session_id=self.session.pk,
                means_of_payment_id=means.pk, amount=amount, created_by=self.user,
            )
        self.assertEqual(self._post(self._payload("48")).status_code, 200)
        summary = self.client.get(f"/api/v1/pos/sessions/{self.session.pk}/summary/").json()
        rows = summary["document_payment_summary"]
        self.assertEqual({row["means"]: Decimal(row["amount"]) for row in rows}, {
            "Efectivo": Decimal("40"), "Yape": Decimal("30"), "Por cobrar al emitir": Decimal("48"),
        })
        self.assertEqual(sum(Decimal(row["amount"]) for row in rows), Decimal("118"))
        self.assertEqual({row["condition"] for row in rows}, {self.credit.name})
        self.assertEqual(Decimal(summary["collection_total"]), Decimal("48"))

    def test_unpaid_credit_document_is_included_in_document_summary(self):
        self._pos_transaction()
        summary = self.client.get(f"/api/v1/pos/sessions/{self.session.pk}/summary/").json()
        self.assertEqual(len(summary["document_payment_summary"]), 1)
        row = summary["document_payment_summary"][0]
        self.assertEqual(row["means"], "Por cobrar al emitir")
        self.assertEqual(Decimal(row["amount"]), Decimal("118"))

    def test_manual_form_credit_date_and_legacy_payment_medium(self):
        series = DocumentSeries.objects.create(
            company=self.company, store=self.store,
            document_type=self.document.document_type, series="NV02",
        )
        form = SalesDocumentHeaderForm(
            company_id=self.company.pk, store_id=self.store.pk,
            document_type=str(self.document.document_type_id),
        )
        self.assertIn("due_date", form.fields)
        self.assertNotIn("means_of_payment", form.fields)
        self.document.status = "DRAFT"
        self.document.series = series
        self.document.means_of_payment = self.cash
        self.document.due_date = None
        self.document.save(update_fields=["status", "series", "means_of_payment", "due_date"])
        response = self.client.post(reverse("sales:document_issue", args=[self.document.pk]))
        self.assertRedirects(response, reverse("sales:document_edit", args=[self.document.pk]), fetch_redirect_response=False)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, "DRAFT")
        self.assertEqual(self.document.means_of_payment, self.cash)

    def test_manual_cash_sale_can_be_collected(self):
        cash_condition = PaymentMethod.objects.create(
            company=self.company, name="Contado", immediate_payment=True,
        )
        self.document.payment_method = cash_condition
        self.document.save(update_fields=["payment_method"])
        self.assertTrue(document_payment_summary(self.document)["can_collect"])
        self.assertEqual(self._post(self._payload()).status_code, 200)
        self.assertEqual(document_payment_summary(self.document)["balance"], Decimal("78"))

    def test_credit_requires_due_date_before_saving_but_blank_condition_does_not(self):
        def check(payment_method, due_date=""):
            form = SalesDocumentHeaderForm(
                data={"payment_method": payment_method, "due_date": due_date},
                company_id=self.company.pk, store_id=self.store.pk,
                document_type=str(self.document.document_type_id),
            )
            form.is_valid()
            return form
        self.assertIn("due_date", check(str(self.credit.pk)).errors)
        self.assertNotIn("due_date", check("").errors)
        self.assertNotIn("due_date", check(str(self.credit.pk), timezone.localdate().isoformat()).errors)

    def test_invalid_sales_form_marks_due_date_and_renders_validation_hooks(self):
        response = self.client.post(reverse("sales:document_create"), {
            "document_type": str(self.document.document_type_id),
            "payment_method": str(self.credit.pk),
            "lines-TOTAL_FORMS": "1", "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1", "lines-MAX_NUM_FORMS": "1000",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Indica la fecha de vencimiento para la venta a crédito.")
        self.assertContains(response, '"id_due_date"')
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'js/sales/document-validation.js')
