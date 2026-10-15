from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.treasury.models import CashSafeCount, CashSafeMovement, TreasuryFund
from apps.users.models import User, UserStore


class CashSafeCountViewTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Arqueos SAC", ruc="20999999991")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.fund = TreasuryFund.objects.create(company=self.company, store=self.store, code="PRINCIPAL", name="Caja fuerte principal", is_default=True)
        self.user = User.objects.create_user(
            email="admin-arqueo@test.local", password="test", is_superuser=True
        )
        UserStore.objects.create(user=self.user, store=self.store, role="ADMIN")
        self.client.force_login(self.user)
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()
        CashSafeMovement.objects.create(
            company=self.company, store=self.store, fund=self.fund, movement_number="CF-BASE",
            direction=CashSafeMovement.Direction.IN,
            movement_type=CashSafeMovement.MovementType.CLOSING_DEPOSIT,
            amount=Decimal("100.00"), currency="PEN",
            status=CashSafeMovement.Status.POSTED, created_by=self.user,
        )

    def test_create_and_close_count_creates_traceable_adjustment(self):
        response = self.client.post(reverse("treasury:cash_safe_count_list"), {
            "action": "create", "counted_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "fund": str(self.fund.pk), "currency": "PEN", "counted_amount": "95.00",
            "denominations": '{"50": 1, "20": 2, "5": 1}', "notes": "Conteo mensual",
        })
        self.assertRedirects(response, reverse("treasury:cash_safe_count_list"))
        count = CashSafeCount.objects.get()
        self.assertEqual(count.count_number, f"ARQ-{timezone.localdate():%Y%m}-0001")
        self.assertEqual(count.theoretical_amount, Decimal("100.00"))
        self.assertEqual(count.difference, Decimal("-5.00"))
        detail_response = self.client.get(
            reverse("treasury:cash_safe_count_detail", args=[count.pk])
        )
        self.assertContains(detail_response, "Dinero virtual")
        self.assertContains(detail_response, count.count_number)

        self.client.post(reverse("treasury:cash_safe_count_list"), {
            "action": "close", "count_id": str(count.pk), "review_notes": "Verificado",
        })
        count.refresh_from_db()
        self.assertEqual(count.status, CashSafeCount.Status.CLOSED)
        self.assertEqual(count.adjustment_movement.direction, CashSafeMovement.Direction.OUT)
        self.assertEqual(count.adjustment_movement.amount, Decimal("5.00"))

    def test_reject_count_does_not_change_cash_safe_balance(self):
        count = CashSafeCount.objects.create(
            company=self.company, store=self.store, fund=self.fund, count_number="ARQ-TEST",
            sequence_number=1,
            counted_at=timezone.now(), currency="PEN", theoretical_amount=Decimal("100.00"),
            counted_amount=Decimal("90.00"), difference=Decimal("-10.00"),
            counted_by=self.user,
        )
        self.client.post(reverse("treasury:cash_safe_count_list"), {
            "action": "reject", "count_id": str(count.pk), "review_notes": "Recontar",
        })
        count.refresh_from_db()
        self.assertEqual(count.status, CashSafeCount.Status.REJECTED)
        self.assertIsNone(count.adjustment_movement)

    def test_historical_count_uses_balance_at_selected_cutoff(self):
        base = CashSafeMovement.objects.get(movement_number="CF-BASE")
        old_time = timezone.now() - timedelta(days=2)
        CashSafeMovement.objects.filter(pk=base.pk).update(created_at=old_time)
        CashSafeMovement.objects.create(
            company=self.company, store=self.store, fund=self.fund,
            movement_number="CF-AFTER", direction=CashSafeMovement.Direction.IN,
            movement_type=CashSafeMovement.MovementType.MANUAL_INCOME,
            amount=Decimal("25.00"), currency="PEN",
            status=CashSafeMovement.Status.POSTED, created_by=self.user,
        )
        cutoff = timezone.now() - timedelta(days=1)

        response = self.client.post(reverse("treasury:cash_safe_count_list"), {
            "action": "create", "counted_at": cutoff.strftime("%Y-%m-%dT%H:%M:%S"),
            "fund": str(self.fund.pk), "currency": "PEN", "counted_amount": "100.00",
            "denominations": '{"50": 2}', "notes": "Corte histórico",
        })

        self.assertRedirects(response, reverse("treasury:cash_safe_count_list"))
        count = CashSafeCount.objects.get()
        self.assertEqual(count.theoretical_amount, Decimal("100.00"))

    def test_denominations_must_match_declared_total(self):
        response = self.client.post(reverse("treasury:cash_safe_count_list"), {
            "action": "create",
            "counted_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M:%S"),
            "fund": str(self.fund.pk), "currency": "PEN", "counted_amount": "100.00",
            "denominations": '{"50": 1}', "notes": "Conteo inconsistente",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "debe coincidir con las denominaciones")
        self.assertFalse(CashSafeCount.objects.exists())
