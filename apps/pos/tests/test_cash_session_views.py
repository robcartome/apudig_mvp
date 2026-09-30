from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.pos.models import CashMovement, CashSession, PosRegister
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
