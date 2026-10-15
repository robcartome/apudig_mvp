from decimal import Decimal
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.pos.models import PosRegister
from apps.treasury.models import CashSafeMovement, CashSafeMovementAttachment, TreasuryFund
from apps.treasury.services import cash_safe_balance
from apps.users.models import User, UserStore


class CashSafeOperationsViewTest(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()
        self.company = Company.objects.create(name="Custodia SAC", ruc="20999999990")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.fund = TreasuryFund.objects.create(company=self.company, store=self.store, code="PRINCIPAL", name="Caja fuerte principal", is_default=True)
        self.user = User.objects.create_user(
            email="treasury-admin@test.local", password="test", is_superuser=True
        )
        UserStore.objects.create(user=self.user, store=self.store, role="ADMIN")
        self.client.force_login(self.user)
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()

    def tearDown(self):
        self.media_override.disable()
        self.media_directory.cleanup()
        super().tearDown()

    def test_manual_income_is_pending_until_approved_and_has_receipt(self):
        response = self.client.post(reverse("treasury:cash_safe_income_create"), {
            "fund": str(self.fund.pk), "currency": "PEN", "amount": "150.00",
            "source_name": "Administrador", "reference": "REP-001",
            "notes": "Reposición autorizada",
        })
        self.assertRedirects(response, reverse("treasury:cash_safe_ledger"))
        movement = CashSafeMovement.objects.get()
        self.assertEqual(movement.direction, CashSafeMovement.Direction.IN)
        self.assertEqual(movement.status, CashSafeMovement.Status.PENDING)
        self.assertEqual(
            cash_safe_balance(
                company_id=self.company.pk, store_id=self.store.pk, currency="PEN"
            ), Decimal("0.00")
        )

        self.client.post(reverse("treasury:cash_safe_ledger"), {
            "action": "approve", "movement_id": str(movement.pk),
        })
        movement.refresh_from_db()
        self.assertEqual(movement.status, CashSafeMovement.Status.POSTED)
        self.assertEqual(
            cash_safe_balance(
                company_id=self.company.pk, store_id=self.store.pk, currency="PEN"
            ), Decimal("150.00")
        )
        detail = self.client.get(
            reverse("treasury:cash_safe_movement_detail", args=[movement.pk])
        )
        self.assertContains(detail, movement.movement_number)
        self.assertContains(detail, "Reposición autorizada")

    def test_cash_safe_csv_export_escapes_spreadsheet_formulas(self):
        CashSafeMovement.objects.create(
            company=self.company, store=self.store, fund=self.fund, movement_number="CF-EXPORT",
            direction=CashSafeMovement.Direction.IN,
            movement_type=CashSafeMovement.MovementType.MANUAL_INCOME,
            amount=Decimal("10.00"), currency="PEN",
            recipient_name="=FORMULA()", notes="Prueba",
            status=CashSafeMovement.Status.POSTED, created_by=self.user,
        )
        response = self.client.get(reverse("treasury:cash_safe_export"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("'=FORMULA()", response.content.decode("utf-8-sig"))

    def test_authenticated_attachment_is_stored_and_downloaded_from_movement(self):
        movement = CashSafeMovement.objects.create(
            company=self.company, store=self.store, fund=self.fund, movement_number="CF-FILE",
            direction=CashSafeMovement.Direction.IN,
            movement_type=CashSafeMovement.MovementType.MANUAL_INCOME,
            amount=Decimal("10.00"), currency="PEN",
            status=CashSafeMovement.Status.POSTED, created_by=self.user,
        )
        response = self.client.post(
            reverse("treasury:cash_safe_movement_detail", args=[movement.pk]),
            {"file": SimpleUploadedFile("voucher.pdf", b"%PDF-1.4 test", "application/pdf")},
        )
        self.assertRedirects(
            response, reverse("treasury:cash_safe_movement_detail", args=[movement.pk])
        )
        attachment = CashSafeMovementAttachment.objects.get(movement=movement)
        response = self.client.get(
            reverse("treasury:cash_safe_attachment_download", args=[attachment.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        response.close()

    def test_each_fund_has_an_independent_available_balance(self):
        secondary = TreasuryFund.objects.create(
            company=self.company, store=self.store, code="CHICA",
            name="Caja chica", fund_type=TreasuryFund.FundType.PETTY_CASH,
        )
        CashSafeMovement.objects.create(
            company=self.company, store=self.store, fund=self.fund,
            movement_number="CF-PRIMARY", direction=CashSafeMovement.Direction.IN,
            movement_type=CashSafeMovement.MovementType.CLOSING_DEPOSIT,
            amount=Decimal("100.00"), currency="PEN",
            status=CashSafeMovement.Status.POSTED, created_by=self.user,
        )

        response = self.client.post(reverse("treasury:cash_safe_ledger"), {
            "action": "request", "fund": str(secondary.pk),
            "movement_type": CashSafeMovement.MovementType.CASH_PAYMENT,
            "currency": "PEN", "amount": "10.00", "recipient_name": "Proveedor",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "saldo disponible")
        self.assertEqual(
            cash_safe_balance(
                company_id=self.company.pk, store_id=self.store.pk,
                currency="PEN", fund_id=secondary.pk,
            ),
            Decimal("0.00"),
        )

    def test_admin_can_create_a_new_physical_fund(self):
        response = self.client.post(reverse("treasury:treasury_fund_list"), {
            "action": "save", "code": "CHICA", "name": "Caja chica",
            "fund_type": TreasuryFund.FundType.PETTY_CASH,
            "notes": "Pagos menores", "active": "on",
        })

        self.assertRedirects(response, reverse("treasury:treasury_fund_list"))
        self.assertTrue(TreasuryFund.objects.filter(
            store=self.store, code="CHICA", name="Caja chica"
        ).exists())

    def test_drawer_transfer_requires_and_stores_destination_register(self):
        register = PosRegister.objects.create(
            company=self.company, store=self.store, code="POS-01", name="Caja principal"
        )
        CashSafeMovement.objects.create(
            company=self.company, store=self.store, fund=self.fund,
            movement_number="CF-DRAWER-BASE",
            direction=CashSafeMovement.Direction.IN,
            movement_type=CashSafeMovement.MovementType.CLOSING_DEPOSIT,
            amount=Decimal("100.00"), currency="PEN",
            status=CashSafeMovement.Status.POSTED, created_by=self.user,
        )

        response = self.client.post(reverse("treasury:cash_safe_ledger"), {
            "action": "request", "fund": str(self.fund.pk),
            "movement_type": CashSafeMovement.MovementType.DRAWER_TRANSFER,
            "destination_register": str(register.pk),
            "currency": "PEN", "amount": "25.00",
            "recipient_name": "Cajero de turno",
        })

        self.assertRedirects(response, reverse("treasury:cash_safe_ledger"))
        movement = CashSafeMovement.objects.get(
            movement_type=CashSafeMovement.MovementType.DRAWER_TRANSFER
        )
        self.assertEqual(movement.destination_register, register)
        self.assertIn(register.code, movement.destination)

    def test_cash_safe_excel_report_uses_current_date_and_fund_filters(self):
        CashSafeMovement.objects.create(
            company=self.company, store=self.store, fund=self.fund,
            movement_number="CF-REPORT", direction=CashSafeMovement.Direction.IN,
            movement_type=CashSafeMovement.MovementType.MANUAL_INCOME,
            amount=Decimal("75.00"), currency="PEN",
            status=CashSafeMovement.Status.POSTED, created_by=self.user,
        )
        today = timezone.localdate().isoformat()
        response = self.client.get(reverse("treasury:cash_safe_export_xlsx"), {
            "date_from": today, "date_to": today, "fund": str(self.fund.pk),
            "currency": "PEN",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertTrue(response.content.startswith(b"PK"))

    def test_approved_fund_transfer_creates_linked_entry_and_reverses_both_sides(self):
        secondary = TreasuryFund.objects.create(
            company=self.company, store=self.store, code="CHICA",
            name="Caja chica", fund_type=TreasuryFund.FundType.PETTY_CASH,
        )
        CashSafeMovement.objects.create(
            company=self.company, store=self.store, fund=self.fund,
            movement_number="CF-TRANSFER-BASE",
            direction=CashSafeMovement.Direction.IN,
            movement_type=CashSafeMovement.MovementType.CLOSING_DEPOSIT,
            amount=Decimal("100.00"), currency="PEN",
            status=CashSafeMovement.Status.POSTED, created_by=self.user,
        )
        response = self.client.post(reverse("treasury:cash_safe_ledger"), {
            "action": "request", "fund": str(self.fund.pk),
            "destination_fund": str(secondary.pk),
            "movement_type": CashSafeMovement.MovementType.FUND_TRANSFER,
            "currency": "PEN", "amount": "40.00",
            "recipient_name": "Responsable de caja chica",
            "notes": "Reposición semanal",
        })
        self.assertRedirects(response, reverse("treasury:cash_safe_ledger"))
        source = CashSafeMovement.objects.get(
            movement_type=CashSafeMovement.MovementType.FUND_TRANSFER,
            direction=CashSafeMovement.Direction.OUT,
        )

        self.client.post(reverse("treasury:cash_safe_ledger"), {
            "action": "approve", "movement_id": str(source.pk),
        })
        source.refresh_from_db()
        counterpart = source.transfer_destination_movement
        self.assertEqual(counterpart.fund, secondary)
        self.assertEqual(counterpart.amount, Decimal("40.00"))
        self.assertEqual(
            cash_safe_balance(
                company_id=self.company.pk, store_id=self.store.pk,
                currency="PEN", fund_id=self.fund.pk,
            ), Decimal("60.00")
        )
        self.assertEqual(
            cash_safe_balance(
                company_id=self.company.pk, store_id=self.store.pk,
                currency="PEN", fund_id=secondary.pk,
            ), Decimal("40.00")
        )

        self.client.post(reverse("treasury:cash_safe_ledger"), {
            "action": "reverse", "movement_id": str(source.pk),
            "reason": "Transferencia registrada por error",
        })
        source.refresh_from_db()
        counterpart.refresh_from_db()
        self.assertEqual(source.status, CashSafeMovement.Status.REVERSED)
        self.assertEqual(counterpart.status, CashSafeMovement.Status.REVERSED)
        self.assertEqual(
            cash_safe_balance(
                company_id=self.company.pk, store_id=self.store.pk,
                currency="PEN", fund_id=self.fund.pk,
            ), Decimal("100.00")
        )
        self.assertEqual(
            cash_safe_balance(
                company_id=self.company.pk, store_id=self.store.pk,
                currency="PEN", fund_id=secondary.pk,
            ), Decimal("0.00")
        )
