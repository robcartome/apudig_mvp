from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, CompanyOperationalSettings, Store
from apps.inventory.models import Product, Unit
from apps.notifications.models import (
    Notification, NotificationPriority, NotificationRecipient,
)
from apps.partners.models import DocumentType, Supplier
from apps.purchases.notification_providers import sync_purchase_payable_notifications
from apps.purchases.payment_services import (
    register_supplier_payment, replace_installment_schedule,
)
from apps.purchases.services import (
    cancel_purchase_document, create_purchase_document_draft,
    register_purchase_document,
)
from apps.sales.models import MeansOfPayment, PaymentMethod
from apps.users.models import Role, UserRole


class NotificationTestBase(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.company = Company.objects.create(name="Empresa avisos", ruc="20988000001")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.supplier = Supplier.objects.create(
            company=self.company, name="Proveedor avisos", document_number="20988000002"
        )
        self.document_type = DocumentType.objects.create(
            code="F-NOT", name="Factura notificación", category="BILLING"
        )
        unit = Unit.objects.create(code="U-NOT", name="Unidad notificación")
        self.product = Product.objects.create(
            company=self.company, name="Servicio notificación", sku="NOT-1",
            unit=unit, tracks_inventory=False,
        )
        self.credit = PaymentMethod.objects.create(
            company=self.company, name="Crédito", is_cash=False,
            is_credit=True, immediate_payment=False, credit_days=30,
        )
        self.cash = PaymentMethod.objects.create(
            company=self.company, name="Contado", is_cash=True,
            is_credit=False, immediate_payment=True,
        )
        self.means = MeansOfPayment.objects.create(company=self.company, name="Banco")
        self.user = get_user_model().objects.create_user(
            email="notificaciones@example.com", password="testpass"
        )
        admin, _ = Role.objects.get_or_create(name="ADMIN")
        UserRole.objects.create(user=self.user, role=admin, company=self.company)
        CompanyOperationalSettings.objects.update_or_create(
            company=self.company, defaults={"purchase_due_notification_days": 3}
        )
        self.sequence = 0

    def document(self, due_date, *, payment_method=None, store=None):
        self.sequence += 1
        document = create_purchase_document_draft(
            company_id=self.company.pk,
            store=store or self.store,
            supplier=self.supplier,
            document_type=self.document_type,
            lines=[{
                "product": self.product, "quantity": 1, "unit_price": 100,
                "tax_type": "20", "igv_rate": 0,
            }],
            series="F001", number=f"{self.sequence:04d}",
            issue_date=self.today - timedelta(days=30),
            due_date=due_date,
            payment_method=payment_method or self.credit,
            register_inventory_movement=False,
        )
        register_purchase_document(document.pk, company_id=self.company.pk)
        return document

    def sync(self, **kwargs):
        return sync_purchase_payable_notifications(
            company_id=self.company.pk, store_id=self.store.pk,
            today=self.today, **kwargs,
        )

    def pay(self, document, amount, number="PAG-NOT-1"):
        return register_supplier_payment(
            company_id=self.company.pk, store=self.store, supplier=self.supplier,
            payment_number=number, payment_date=timezone.now(), currency="PEN",
            exchange_rate=1, means_of_payment=self.means,
            allocations=[{"installment": document.installments.get(), "amount": amount}],
            created_by=self.user,
        )


class PurchaseNotificationProviderTest(NotificationTestBase):
    def test_upcoming_invoice_uses_configurable_three_day_threshold(self):
        self.document(self.today + timedelta(days=3))
        self.document(self.today + timedelta(days=4))
        self.sync()
        self.assertEqual(Notification.objects.filter(is_active=True).count(), 1)
        self.assertEqual(Notification.objects.get().priority, NotificationPriority.WARNING)

    def test_invoice_due_today_generates_warning(self):
        document = self.document(self.today)
        self.sync()
        notification = Notification.objects.get()
        self.assertIn("próxima a vencer", notification.title)
        self.assertEqual(notification.metadata["purchase_document_id"], str(document.pk))

    def test_overdue_invoice_contains_days_supplier_and_balance(self):
        self.document(self.today - timedelta(days=5))
        self.sync()
        notification = Notification.objects.get()
        self.assertEqual(notification.priority, NotificationPriority.HIGH)
        self.assertEqual(notification.metadata["overdue_days"], 5)
        self.assertEqual(notification.amount, Decimal("100.00"))
        self.assertIn(self.supplier.name, notification.message)

    def test_partial_payment_updates_balance_and_full_payment_resolves(self):
        document = self.document(self.today - timedelta(days=2))
        self.pay(document, Decimal("40"))
        self.sync()
        notification = Notification.objects.get()
        self.assertEqual(notification.amount, Decimal("60.00"))
        self.pay(document, Decimal("60"), "PAG-NOT-2")
        self.sync()
        notification.refresh_from_db()
        self.assertFalse(notification.is_active)
        self.assertIsNotNone(notification.resolved_at)

    def test_cancelled_and_cash_documents_do_not_remain_active(self):
        credit_document = self.document(self.today - timedelta(days=1))
        self.document(self.today, payment_method=self.cash)
        self.sync()
        self.assertEqual(Notification.objects.filter(is_active=True).count(), 1)
        cancel_purchase_document(credit_document.pk, company_id=self.company.pk)
        self.sync()
        self.assertFalse(Notification.objects.get().is_active)

    def test_each_installment_generates_one_notification_without_duplicates(self):
        document = self.document(self.today + timedelta(days=2))
        replace_installment_schedule(document.pk, company_id=self.company.pk, schedule=[
            {"due_date": self.today - timedelta(days=1), "amount": Decimal("40")},
            {"due_date": self.today + timedelta(days=2), "amount": Decimal("60")},
        ])
        self.sync()
        self.sync()
        notifications = Notification.objects.filter(is_active=True)
        self.assertEqual(notifications.count(), 2)
        self.assertEqual(
            set(notifications.values_list("amount", flat=True)),
            {Decimal("40.00"), Decimal("60.00")},
        )

    def test_changed_due_date_resolves_old_installment_event(self):
        document = self.document(self.today + timedelta(days=2))
        self.sync(document_id=document.pk)
        old_notification = Notification.objects.get()
        replace_installment_schedule(document.pk, company_id=self.company.pk, schedule=[
            {"due_date": self.today + timedelta(days=10), "amount": Decimal("100")},
        ])
        self.sync(document_id=document.pk)
        old_notification.refresh_from_db()
        self.assertFalse(old_notification.is_active)

    def test_recipients_are_isolated_by_company(self):
        other_company = Company.objects.create(name="Otra empresa", ruc="20988000003")
        other_user = get_user_model().objects.create_user(email="otra@example.com")
        admin = Role.objects.get(name="ADMIN")
        UserRole.objects.create(user=other_user, role=admin, company=other_company)
        self.document(self.today - timedelta(days=1))
        self.sync()
        self.assertTrue(NotificationRecipient.objects.filter(user=self.user).exists())
        self.assertFalse(NotificationRecipient.objects.filter(user=other_user).exists())


class NotificationViewTest(NotificationTestBase):
    def setUp(self):
        super().setUp()
        self.overdue = self.document(self.today - timedelta(days=2))
        self.upcoming = self.document(self.today + timedelta(days=2))
        self.sync()
        self.client.login(username=self.user.email, password="testpass")
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()

    def test_dropdown_and_full_page_expose_persisted_notifications(self):
        response = self.client.get(reverse("notifications:dropdown"), {"status": "unread"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["unread_count"], 2)
        self.assertIn("Proveedor avisos", response.json()["html"])
        page = self.client.get(reverse("notifications:list"))
        self.assertContains(page, "Centro de notificaciones")
        self.assertContains(page, "Compra F001-")

    def test_individual_and_bulk_read_actions_update_unread_count(self):
        first = NotificationRecipient.objects.filter(user=self.user).first()
        response = self.client.post(
            reverse("notifications:mark_read", args=[first.notification_id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["unread_count"], 1)
        response = self.client.post(reverse("notifications:mark_all_read"))
        self.assertEqual(response.json()["unread_count"], 0)
        self.assertFalse(
            NotificationRecipient.objects.filter(user=self.user, read_at__isnull=True).exists()
        )

    def test_navbar_has_compact_async_component_and_empty_badge(self):
        response = self.client.get(reverse("purchases:document_list"))
        self.assertContains(response, 'data-notification-center', html=False)
        self.assertContains(response, 'data-notification-tab="unread"', html=False)
        self.assertContains(response, 'data-notification-read-all', html=False)
        self.assertContains(response, "js/components/notifications")

