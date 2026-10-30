from django.core.management.base import BaseCommand

from apps.notifications.models import (
    Notification, NotificationRecipient, NotificationType,
)
from apps.purchases.notification_providers import sync_purchase_payable_notifications


class Command(BaseCommand):
    help = "Sincroniza las notificaciones empresariales activas."

    def add_arguments(self, parser):
        parser.add_argument("--company", dest="company_id")
        parser.add_argument("--store", dest="store_id")

    def handle(self, *args, **options):
        count = sync_purchase_payable_notifications(
            company_id=options.get("company_id"),
            store_id=options.get("store_id"),
        )
        notifications = Notification.objects.filter(
            is_active=True,
            notification_type=NotificationType.PURCHASE_DUE,
        )
        recipients = NotificationRecipient.objects.filter(
            notification__is_active=True,
            notification__notification_type=NotificationType.PURCHASE_DUE,
        )
        if options.get("company_id"):
            notifications = notifications.filter(company_id=options["company_id"])
            recipients = recipients.filter(notification__company_id=options["company_id"])
        if options.get("store_id"):
            notifications = notifications.filter(store_id=options["store_id"])
            recipients = recipients.filter(notification__store_id=options["store_id"])
        self.stdout.write(self.style.SUCCESS(
            "Sincronización completada: "
            f"{count} obligaciones evaluadas, "
            f"{notifications.count()} avisos activos, "
            f"{recipients.count()} destinatarios."
        ))

