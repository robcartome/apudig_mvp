from datetime import timedelta
from uuid import UUID
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.websites.models import CommercialRegistration


class Command(BaseCommand):
    help = "Purge one Website's expired registration PII according to its accepted notice. Dry-run by default."

    def add_arguments(self, parser):
        parser.add_argument("--website", required=True, type=UUID)
        parser.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        now, eligible, deleted = timezone.now(), 0, 0
        rows = CommercialRegistration.objects.filter(website_id=options["website"]).exclude(websiteemailoutbox__status="SENDING").select_related("notice")
        for row in rows.iterator(chunk_size=100):
            if row.created_at + timedelta(days=row.notice.pending_retention_days) < now:
                eligible += 1
                if options["execute"]:
                    row.delete()
                    deleted += 1
        self.stdout.write(f"eligible={eligible} deleted={deleted}")
