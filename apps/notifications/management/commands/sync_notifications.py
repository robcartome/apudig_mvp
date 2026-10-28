from django.core.management.base import BaseCommand

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
        self.stdout.write(self.style.SUCCESS(f"Notificaciones sincronizadas: {count}"))

