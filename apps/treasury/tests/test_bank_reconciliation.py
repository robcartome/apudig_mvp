from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.treasury.models import (
    Bank,
    BankAccount,
    BankMovement,
    BankReconciliationMatch,
    BankStatement,
)
from apps.users.models import User, UserStore


class BankReconciliationViewTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Conciliación SAC", ruc="20999999992")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.user = User.objects.create_user(
            email="reconcile@test.local", password="test", is_staff=True, is_superuser=True
        )
        UserStore.objects.create(user=self.user, store=self.store, role="ADMIN")
        self.bank = Bank.objects.create(company=self.company, name="Banco Demo")
        self.today = timezone.localdate()
        self.account = BankAccount.objects.create(
            company=self.company,
            bank=self.bank,
            name="Cuenta principal",
            account_number="001-100",
            opening_balance=Decimal("1000.00"),
            opening_balance_date=self.today,
        )
        self.movement = BankMovement.objects.create(
            company=self.company,
            account=self.account,
            movement_number="BM-TEST-001",
            direction=BankMovement.Direction.OUT,
            movement_type=BankMovement.MovementType.PAYMENT,
            amount=Decimal("100.00"),
            operation_date=self.today,
            reference="PAGO-1",
            description="Pago a proveedor",
            created_by=self.user,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()

    def _import_statement(self):
        content = (
            "fecha,descripcion,referencia,cargo,abono\n"
            f"{self.today:%d/%m/%Y},Pago a proveedor,PAGO-1,100.00,\n"
        ).encode()
        response = self.client.post(reverse("treasury:bank_reconciliation_list"), {
            "account": str(self.account.pk),
            "date_from": self.today.isoformat(),
            "date_to": self.today.isoformat(),
            "opening_balance": "1000.00",
            "closing_balance": "900.00",
            "statement_file": SimpleUploadedFile("estado.csv", content, "text/csv"),
        })
        statement = BankStatement.objects.get(account=self.account)
        self.assertRedirects(
            response, reverse("treasury:bank_reconciliation_detail", args=[statement.pk])
        )
        return statement

    def test_import_match_and_close_statement(self):
        statement = self._import_statement()
        line = statement.lines.get()

        response = self.client.get(
            reverse("treasury:bank_reconciliation_detail", args=[statement.pk])
        )
        self.assertContains(response, self.movement.movement_number)

        response = self.client.post(
            reverse("treasury:bank_reconciliation_detail", args=[statement.pk]),
            {"action": "match", "line_id": str(line.pk), "movement_id": str(self.movement.pk)},
        )
        self.assertRedirects(
            response, reverse("treasury:bank_reconciliation_detail", args=[statement.pk])
        )
        self.assertTrue(BankReconciliationMatch.objects.filter(statement_line=line).exists())

        self.client.post(
            reverse("treasury:bank_reconciliation_detail", args=[statement.pk]),
            {"action": "close"},
        )
        statement.refresh_from_db()
        self.assertEqual(statement.status, BankStatement.Status.RECONCILED)
        self.assertEqual(statement.reconciled_by, self.user)

    def test_cannot_close_with_unmatched_lines(self):
        statement = self._import_statement()

        response = self.client.post(
            reverse("treasury:bank_reconciliation_detail", args=[statement.pk]),
            {"action": "close"},
            follow=True,
        )

        statement.refresh_from_db()
        self.assertEqual(statement.status, BankStatement.Status.DRAFT)
        self.assertContains(response, "sin conciliar")

    def test_one_bank_line_can_match_multiple_system_movements(self):
        self.movement.delete()
        movements = [
            BankMovement.objects.create(
                company=self.company, account=self.account,
                movement_number=f"BM-GROUP-{index}",
                direction=BankMovement.Direction.OUT,
                movement_type=BankMovement.MovementType.PAYMENT,
                amount=amount, operation_date=self.today,
                description=f"Pago agrupado {index}", created_by=self.user,
            )
            for index, amount in enumerate((Decimal("40.00"), Decimal("60.00")), start=1)
        ]
        statement = self._import_statement()
        line = statement.lines.get()

        for movement in movements:
            self.client.post(
                reverse("treasury:bank_reconciliation_detail", args=[statement.pk]),
                {"action": "match", "line_id": str(line.pk), "movement_id": str(movement.pk)},
            )

        self.assertEqual(
            BankReconciliationMatch.objects.filter(statement_line=line).count(), 2
        )
        self.client.post(
            reverse("treasury:bank_reconciliation_detail", args=[statement.pk]),
            {"action": "close"},
        )
        statement.refresh_from_db()
        self.assertEqual(statement.status, BankStatement.Status.RECONCILED)
