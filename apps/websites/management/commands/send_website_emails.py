from django.core.management.base import BaseCommand, CommandError
from apps.websites.models import WebsiteEmailOutbox
from apps.websites.registration_mail import send_queued_emails
from apps.websites.errors import WebsiteError


class Command(BaseCommand):
    help = "Inspect the Website mail queue; --send explicitly performs external SMTP delivery."

    def add_arguments(self, parser):
        parser.add_argument("--send", action="store_true")
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        if not options["send"]:
            self.stdout.write(f"dry_run queued={WebsiteEmailOutbox.objects.filter(status__in=('QUEUED', 'FAILED')).count()}")
            return
        try:
            result = send_queued_emails(limit=options["limit"])
        except WebsiteError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"sent={result['sent']} failed={result['failed']}")
        if result["failed"]:
            raise CommandError("Some deliveries failed; only sanitized error codes were retained.")
