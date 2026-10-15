from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.pos.models import CashMovement, CashSession, PosRegister
from apps.treasury.models import CashSafeMovement, TreasuryFund
from apps.pos.permissions import POS_PERMISSION_DEFINITIONS
from apps.users.models import Permission, Role, RolePermission, User, UserStore


class CashSessionHistoryViewTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Ferretería Caja", ruc="20999999991")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.register = PosRegister.objects.create(
            company=self.company, store=self.store, code="POS-01", name="Caja principal"
        )
        self.cashier_role, _ = Role.objects.get_or_create(name="CASHIER")
        self.cashier = User.objects.create_user(email="cashier-history@test.local", password="test")
        self.other_cashier = User.objects.create_user(email="other-history@test.local", password="test")
        for user in (self.cashier, self.other_cashier):
            UserStore.objects.create(user=user, store=self.store, role="CASHIER")
        self._grant(self.cashier_role, "read.pos.cash_sessions")
        self.own_session = CashSession.objects.create(
            register=self.register,
            company=self.company,
            store=self.store,
            opened_by=self.cashier,
            opening_total=Decimal("100.00"),
            session_number=1,
        )
        self.other_session = CashSession.objects.create(
            register=self.register,
            company=self.company,
            store=self.store,
            opened_by=self.other_cashier,
            opening_total=Decimal("50.00"),
            session_number=2,
            status=CashSession.Status.CLOSED,
            closed_by=self.other_cashier,
            closed_at=self.own_session.opened_at,
            expected_cash_total=Decimal("50.00"),
            counted_cash_total=Decimal("50.00"),
            cash_difference=Decimal("0.00"),
        )

    def _grant(self, role, code):
        action, module, description = next(
            item for item in POS_PERMISSION_DEFINITIONS if f"{item[0]}.{item[1]}" == code
        )
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={"action_name": action, "module": module, "description": description},
        )
        RolePermission.objects.get_or_create(role=role, permission=permission)

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()

    def test_cashier_only_sees_sessions_opened_by_them(self):
        self._login(self.cashier)

        response = self.client.get(reverse("pos:cash_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("pos:cash_session_detail", args=(self.own_session.pk,)))
        self.assertNotContains(response, reverse("pos:cash_session_detail", args=(self.other_session.pk,)))

    def test_cashier_cannot_open_another_cashiers_session_detail(self):
        self._login(self.cashier)

        response = self.client.get(
            reverse("pos:cash_session_detail", args=(self.other_session.pk,))
        )

        self.assertEqual(response.status_code, 404)

    def test_company_admin_can_filter_and_audit_all_sessions(self):
        admin = User.objects.create_user(email="admin-history@test.local", password="test")
        UserStore.objects.create(user=admin, store=self.store, role="ADMIN")
        self._login(admin)

        response = self.client.get(reverse("pos:cash_session_list"), {
            "cashier": str(self.other_cashier.pk),
            "status": CashSession.Status.CLOSED,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("pos:cash_session_detail", args=(self.other_session.pk,)))
        self.assertNotContains(response, reverse("pos:cash_session_detail", args=(self.own_session.pk,)))

    def test_session_detail_displays_live_summary_and_movement(self):
        CashMovement.objects.create(
            cash_session=self.own_session,
            movement_type=CashMovement.MovementType.PAY_IN,
            amount=Decimal("20.00"),
            description="Ingreso de sencillo",
            created_by=self.cashier,
        )
        self._login(self.cashier)

        response = self.client.get(
            reverse("pos:cash_session_detail", args=(self.own_session.pk,))
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resumen")
        self.assertContains(response, "Ventas")
        self.assertContains(response, "Movimientos")
        self.assertContains(response, "Pagos")
        self.assertContains(response, "Ingreso de sencillo")
        self.assertContains(response, "120,00")
        self.assertContains(response, "Resumen del día")
        self.assertContains(response, "Resumen por medio de pago")
        self.assertContains(response, "Detalle Vale de Ingreso")
        self.assertContains(response, "Detalle Vale de Salida")
        self.assertContains(response, "financial-report.css")

    def test_invalid_uuid_filter_is_ignored_safely(self):
        self._login(self.cashier)

        response = self.client.get(reverse("pos:cash_session_list"), {"register": "invalid"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("pos:cash_session_detail", args=(self.own_session.pk,)))

    def test_daily_consult_filters_closures_to_selected_day(self):
        admin = User.objects.create_user(email="admin-daily@test.local", password="test")
        UserStore.objects.create(user=admin, store=self.store, role="ADMIN")
        yesterday = timezone.now() - timedelta(days=1)
        CashSession.objects.filter(pk=self.other_session.pk).update(
            opened_at=yesterday, closed_at=yesterday
        )
        self._login(admin)

        response = self.client.get(reverse("pos:cash_session_list"), {
            "daily_date": self.own_session.opened_at.date().isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("pos:cash_session_detail", args=(self.own_session.pk,)))
        self.assertNotContains(response, reverse("pos:cash_session_detail", args=(self.other_session.pk,)))
        self.assertEqual(response.context["date_from"], self.own_session.opened_at.date().isoformat())
        self.assertEqual(response.context["date_to"], self.own_session.opened_at.date().isoformat())


    def test_cash_session_report_download_respects_date_filters(self):
        self._login(self.cashier)
        today = timezone.localdate().isoformat()
        response = self.client.get(reverse("pos:cash_session_export"), {
            "date_from": today, "date_to": today,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertTrue(response.content.startswith(b"PK"))


class CashSafeLedgerViewTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Tesorería Test", ruc="20999999992")
        self.store = Store.objects.create(company=self.company, name="Tienda principal")
        self.fund = TreasuryFund.objects.create(company=self.company, store=self.store, code="PRINCIPAL", name="Caja fuerte principal", is_default=True)
        self.admin = User.objects.create_user(email="treasury@test.local", password="test")
        UserStore.objects.create(user=self.admin, store=self.store, role="ADMIN")
        self.client.force_login(self.admin)
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()

    def _movement(self, **overrides):
        values = {
            "company": self.company,
            "store": self.store,
            "fund": self.fund,
            "direction": CashSafeMovement.Direction.IN,
            "movement_type": CashSafeMovement.MovementType.CLOSING_DEPOSIT,
            "amount": Decimal("100.00"),
            "currency": "PEN",
            "recipient_name": "",
            "destination": "Caja fuerte de tienda",
            "created_by": self.admin,
        }
        values.update(overrides)
        return CashSafeMovement.objects.create(**values)

    def test_sidebar_exposes_treasury_and_store_safe(self):
        response = self.client.get(reverse("treasury:cash_safe_ledger"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tesorería")
        self.assertContains(response, "Caja fuerte de tienda")

    def test_filters_movements_by_currency_direction_type_and_search(self):
        visible = self._movement(recipient_name="María Responsable", reference="DEP-001")
        self._movement(
            direction=CashSafeMovement.Direction.OUT,
            movement_type=CashSafeMovement.MovementType.BANK_DEPOSIT,
            amount=Decimal("20.00"),
            currency="USD",
            recipient_name="Otra persona",
        )

        response = self.client.get(reverse("treasury:cash_safe_ledger"), {
            "currency": "PEN",
            "direction": CashSafeMovement.Direction.IN,
            "movement_type": CashSafeMovement.MovementType.CLOSING_DEPOSIT,
            "q": "María",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["movements"]), [visible])
        self.assertEqual(response.context["filtered_incoming"], Decimal("100.00"))
        self.assertEqual(response.context["filtered_outgoing"], Decimal("0.00"))

    def test_ledger_is_paginated(self):
        for number in range(51):
            self._movement(reference=f"MOV-{number:03d}")

        response = self.client.get(reverse("treasury:cash_safe_ledger"))

        self.assertEqual(response.context["page_obj"].paginator.count, 51)
        self.assertEqual(len(response.context["movements"]), 50)
        self.assertContains(response, "Siguiente")

    def test_legacy_pos_url_redirects_to_treasury(self):
        response = self.client.get(reverse("pos:cash_safe_ledger"))

        self.assertRedirects(
            response, reverse("treasury:cash_safe_ledger"),
            fetch_redirect_response=False,
        )

    def test_withdrawal_cannot_exceed_available_balance(self):
        self._movement(amount=Decimal("100.00"))

        response = self.client.post(reverse("treasury:cash_safe_ledger"), {
            "movement_type": CashSafeMovement.MovementType.CASH_PAYMENT,
            "currency": "PEN",
            "amount": "100.01",
            "recipient_name": "Proveedor",
            "destination": "Pago de prueba",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "supera el saldo disponible")
        self.assertEqual(
            CashSafeMovement.objects.filter(direction=CashSafeMovement.Direction.OUT).count(),
            0,
        )

    def test_withdrawal_can_be_approved_by_another_admin_and_reversed(self):
        self._movement(amount=Decimal("100.00"))
        response = self.client.post(reverse("treasury:cash_safe_ledger"), {
            "action": "request",
            "movement_type": CashSafeMovement.MovementType.CASH_PAYMENT,
            "currency": "PEN",
            "amount": "40.00",
            "recipient_name": "Proveedor",
            "destination": "Factura F001-10",
        })
        self.assertRedirects(response, reverse("treasury:cash_safe_ledger"))
        withdrawal = CashSafeMovement.objects.get(
            direction=CashSafeMovement.Direction.OUT
        )
        self.assertEqual(withdrawal.status, CashSafeMovement.Status.PENDING)
        self.assertTrue(withdrawal.movement_number.startswith("CF-"))

        approver = User.objects.create_user(email="approver@test.local", password="test")
        UserStore.objects.create(user=approver, store=self.store, role="ADMIN")
        self.client.force_login(approver)
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()
        response = self.client.post(reverse("treasury:cash_safe_ledger"), {
            "action": "approve", "movement_id": str(withdrawal.pk),
        })
        self.assertRedirects(response, reverse("treasury:cash_safe_ledger"))
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, CashSafeMovement.Status.POSTED)
        self.assertEqual(withdrawal.authorized_by, approver)
        self.assertIsNotNone(withdrawal.authorized_at)

        response = self.client.post(reverse("treasury:cash_safe_ledger"), {
            "action": "reverse", "movement_id": str(withdrawal.pk),
            "reason": "Documento registrado por error",
        })
        self.assertRedirects(response, reverse("treasury:cash_safe_ledger"))
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, CashSafeMovement.Status.REVERSED)
        reversal = CashSafeMovement.objects.get(reversed_movement=withdrawal)
        self.assertEqual(reversal.direction, CashSafeMovement.Direction.IN)
        self.assertEqual(reversal.amount, Decimal("40.00"))

    def test_admin_can_confirm_own_withdrawal_with_audit_identity(self):
        self._movement(amount=Decimal("100.00"))
        self.client.post(reverse("treasury:cash_safe_ledger"), {
            "action": "request",
            "movement_type": CashSafeMovement.MovementType.CASH_PAYMENT,
            "currency": "PEN",
            "amount": "25.00",
            "recipient_name": "Proveedor local",
            "destination": "Pago urgente",
        })
        withdrawal = CashSafeMovement.objects.get(
            direction=CashSafeMovement.Direction.OUT
        )

        response = self.client.post(reverse("treasury:cash_safe_ledger"), {
            "action": "approve", "movement_id": str(withdrawal.pk),
        })

        self.assertRedirects(response, reverse("treasury:cash_safe_ledger"))
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, CashSafeMovement.Status.POSTED)
        self.assertEqual(withdrawal.authorized_by, self.admin)
        self.assertIsNotNone(withdrawal.authorized_at)
