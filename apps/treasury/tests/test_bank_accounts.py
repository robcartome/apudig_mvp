from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.users.models import User, UserStore
from apps.treasury.models import BankAccount, BankMovement, CashSafeMovement, TreasuryFund
from apps.treasury.services import bank_account_balance


class TreasuryBankAccountViewTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Tesorería Bancos", ruc="20999999993")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.fund = TreasuryFund.objects.create(company=self.company, store=self.store, code="PRINCIPAL", name="Caja fuerte principal", is_default=True)
        self.user = User.objects.create_user(
            email="bank@test.local", password="test", is_staff=True, is_superuser=True
        )
        UserStore.objects.create(user=self.user, store=self.store, role="ADMIN")
        self.client.force_login(self.user)
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()

    def _create_account(self):
        response = self.client.post(reverse("treasury:bank_account_create"), {
            "bank_name": "Banco de Crédito del Perú",
            "name": "Cuenta corriente principal",
            "account_type": BankAccount.AccountType.CHECKING,
            "currency": "PEN",
            "account_number": "3552387523050",
            "cci": "00235512387523050123",
            "opening_balance": "1000.00",
            "opening_balance_date": timezone.localdate().isoformat(),
            "accounting_account": "104111",
            "max_transfer_amount": "500.00",
            "use_for_payments": "on",
            "active": "on",
        })
        self.assertRedirects(
            response, f"{reverse('users:configuracion')}?item=cuentas_bancarias"
        )
        return BankAccount.objects.get(company=self.company)

    def test_create_account_and_display_masked_number(self):
        account = self._create_account()

        response = self.client.get(reverse("treasury:dashboard"))

        self.assertContains(response, "Cuenta corriente principal")
        self.assertContains(response, "•••• 3050")
        self.assertNotContains(response, "3552387523050")
        self.assertEqual(account.opening_balance, Decimal("1000.00"))

    def test_account_is_listed_from_company_settings(self):
        account = self._create_account()

        response = self.client.get(
            reverse("users:configuracion"), {"item": "cuentas_bancarias"}
        )

        self.assertContains(response, "Cuentas bancarias")
        self.assertContains(response, account.bank.name)
        self.assertContains(response, account.masked_number)
        self.assertNotContains(response, account.account_number)

    def test_register_bank_movement_updates_system_balance(self):
        account = self._create_account()

        response = self.client.post(reverse("treasury:bank_expense_list"), {
            "form_kind": "movement",
            "account": str(account.pk),
            "movement_type": BankMovement.MovementType.PAYMENT,
            "amount": "250.00",
            "operation_date": timezone.localdate().isoformat(),
            "reference": "OP-100",
            "description": "Pago a proveedor",
        })

        self.assertRedirects(response, reverse("treasury:bank_expense_list"))
        movement = BankMovement.objects.get(account=account)
        self.assertTrue(movement.movement_number.startswith("BM-"))
        self.assertEqual(bank_account_balance(account), Decimal("750.00"))

    def test_transfer_over_account_limit_is_rejected(self):
        account = self._create_account()
        destination = BankAccount.objects.create(
            company=self.company, bank=account.bank, name="Cuenta destino",
            account_number="3552387523999", currency="PEN",
            opening_balance=Decimal("0.00"),
            opening_balance_date=timezone.localdate(),
        )

        response = self.client.post(reverse("treasury:bank_expense_list"), {
            "form_kind": "movement",
            "account": str(account.pk),
            "destination_account": str(destination.pk),
            "movement_type": BankMovement.MovementType.TRANSFER,
            "amount": "600.00",
            "operation_date": timezone.localdate().isoformat(),
            "reference": "OP-LIMIT",
            "description": "Pago fuera del limite",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "supera el límite configurado")
        self.assertFalse(BankMovement.objects.filter(account=account).exists())

    def test_internal_transfer_creates_both_sides_and_can_be_reversed(self):
        account = self._create_account()
        destination = BankAccount.objects.create(
            company=self.company, bank=account.bank, name="Cuenta destino",
            account_number="3552387523888", currency="PEN",
            opening_balance=Decimal("100.00"),
            opening_balance_date=timezone.localdate(),
        )
        response = self.client.post(reverse("treasury:bank_expense_list"), {
            "form_kind": "movement", "account": str(account.pk),
            "destination_account": str(destination.pk),
            "movement_type": BankMovement.MovementType.TRANSFER,
            "amount": "300.00", "operation_date": timezone.localdate().isoformat(),
            "reference": "TR-001", "description": "Transferencia entre cuentas",
        })
        self.assertRedirects(response, reverse("treasury:bank_expense_list"))
        outgoing = BankMovement.objects.get(account=account, direction=BankMovement.Direction.OUT)
        incoming = BankMovement.objects.get(transfer_source=outgoing)
        self.assertEqual(bank_account_balance(account), Decimal("700.00"))
        self.assertEqual(bank_account_balance(destination), Decimal("400.00"))

        response = self.client.post(reverse("treasury:bank_expense_list"), {
            "form_kind": "reverse", "movement_id": str(outgoing.pk),
            "reason": "Transferencia registrada por error",
        })
        self.assertRedirects(response, reverse("treasury:bank_expense_list"))
        outgoing.refresh_from_db()
        incoming.refresh_from_db()
        self.assertEqual(outgoing.status, BankMovement.Status.REVERSED)
        self.assertEqual(incoming.status, BankMovement.Status.REVERSED)
        self.assertEqual(bank_account_balance(account), Decimal("1000.00"))
        self.assertEqual(bank_account_balance(destination), Decimal("100.00"))

    def test_opening_balance_is_locked_after_account_activity(self):
        account = self._create_account()
        BankMovement.objects.create(
            company=self.company, account=account, movement_number="BM-LOCK-1",
            direction=BankMovement.Direction.IN,
            movement_type=BankMovement.MovementType.RECEIPT,
            amount=Decimal("10.00"), operation_date=timezone.localdate(),
            description="Movimiento inicial", created_by=self.user,
        )
        response = self.client.post(
            reverse("treasury:bank_account_update", args=[account.pk]), {
                "bank_name": account.bank.name, "name": account.name,
                "account_type": account.account_type, "currency": account.currency,
                "account_number": account.account_number,
                "opening_balance": "1200.00",
                "opening_balance_date": account.opening_balance_date.isoformat(),
                "max_transfer_amount": "500.00", "use_for_payments": "on",
                "active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "saldo inicial no puede modificarse")
        account.refresh_from_db()
        self.assertEqual(account.opening_balance, Decimal("1000.00"))

    def test_income_page_forces_income_direction(self):
        account = self._create_account()

        response = self.client.post(reverse("treasury:bank_income_list"), {
            "form_kind": "movement",
            "account": str(account.pk),
            "movement_type": BankMovement.MovementType.RECEIPT,
            "amount": "125.00",
            "operation_date": timezone.localdate().isoformat(),
            "reference": "ING-001",
            "description": "Ingreso extraordinario",
        })

        self.assertRedirects(response, reverse("treasury:bank_income_list"))
        movement = BankMovement.objects.get(account=account)
        self.assertEqual(movement.direction, BankMovement.Direction.IN)

        response = self.client.get(reverse("treasury:bank_income_list"))
        self.assertContains(response, "Ingresos bancarios")
        self.assertContains(response, "Ingreso extraordinario")

    def test_bank_movement_report_respects_account_and_date_filters(self):
        account = self._create_account()
        BankMovement.objects.create(
            company=self.company, account=account, movement_number="BM-REPORT-1",
            direction=BankMovement.Direction.IN,
            movement_type=BankMovement.MovementType.RECEIPT,
            amount=Decimal("125.00"), operation_date=timezone.localdate(),
            description="Ingreso para reporte", created_by=self.user,
        )
        today = timezone.localdate().isoformat()

        response = self.client.get(reverse("treasury:bank_movement_export_xlsx"), {
            "account": str(account.pk), "direction": BankMovement.Direction.IN,
            "date_from": today, "date_to": today,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertTrue(response.content.startswith(b"PK"))

    def test_safe_deposit_creates_bank_income_only_after_real_deposit_confirmation(self):
        account = self._create_account()
        CashSafeMovement.objects.create(
            company=self.company, store=self.store, fund=self.fund,
            direction=CashSafeMovement.Direction.IN,
            movement_type=CashSafeMovement.MovementType.CLOSING_DEPOSIT,
            amount=Decimal("500.00"), currency="PEN",
            movement_number="CF-OPENING", created_by=self.user,
        )
        response = self.client.post(reverse("treasury:cash_safe_ledger"), {
            "action": "request",
            "fund": str(self.fund.pk),
            "movement_type": CashSafeMovement.MovementType.BANK_DEPOSIT,
            "currency": "PEN", "amount": "200.00",
            "recipient_name": "Administrador",
            "bank_account": str(account.pk),
            "reference": "DEP-001",
        })
        self.assertRedirects(response, reverse("treasury:cash_safe_ledger"))
        request_movement = CashSafeMovement.objects.get(
            movement_type=CashSafeMovement.MovementType.BANK_DEPOSIT
        )
        approver = User.objects.create_user(email="bank-approver@test.local", password="test")
        UserStore.objects.create(user=approver, store=self.store, role="ADMIN")
        self.client.force_login(approver)
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()
        response = self.client.post(reverse("treasury:cash_safe_ledger"), {
            "action": "approve", "movement_id": str(request_movement.pk),
        })

        self.assertRedirects(response, reverse("treasury:cash_safe_ledger"))
        self.assertFalse(BankMovement.objects.filter(safe_movement=request_movement).exists())
        tracking = request_movement.deposit_tracking
        self.assertEqual(tracking.status, "IN_TRANSIT")
        self.assertEqual(bank_account_balance(account), Decimal("1000.00"))

        response = self.client.post(reverse("treasury:cash_safe_deposit_list"), {
            "deposit_id": str(tracking.pk),
            "operation_date": timezone.localdate().isoformat(),
            "operation_reference": "DEP-001",
            "confirmation_notes": "Voucher verificado",
        })
        self.assertRedirects(response, reverse("treasury:cash_safe_deposit_list"))
        bank_movement = BankMovement.objects.get(safe_movement=request_movement)
        self.assertEqual(bank_movement.direction, BankMovement.Direction.IN)
        self.assertEqual(bank_movement.amount, Decimal("200.00"))
        self.assertEqual(bank_account_balance(account), Decimal("1200.00"))
