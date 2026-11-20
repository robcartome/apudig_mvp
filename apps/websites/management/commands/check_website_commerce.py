"""Read-only technical readiness, never an operational approval."""
import json

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor

from apps.websites.models import Website
from apps.websites.selectors import resolve_public_website
from apps.websites.commerce import commerce_enabled, commerce_readiness
from apps.websites.registration_mail import provider_ready
from apps.websites.registration import public_registration_policy


class Command(BaseCommand):
    help = "Inspect one published Website without writes, network probes or secrets."

    def add_arguments(self, parser):
        parser.add_argument("--hostname", required=True)

    def handle(self, *args, **options):
        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION READ ONLY")
            executor = MigrationExecutor(connection)
            executor.loader.check_consistent_history(connection)
            context = resolve_public_website(options["hostname"])
            website = Website.objects.select_related("company", "published_revision__page").get(pk=context.website_id)
            required_storage = ("R2_BUCKET_NAME", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_PUBLIC_BASE_URL")
            report = {
                "hostname": context.hostname, "engine": connection.vendor,
                "pendingMigrations": [f"{migration.app_label}.{migration.name}" for migration, _ in executor.migration_plan(executor.loader.graph.leaf_nodes())],
                "commerceEnabled": commerce_enabled(website.pk),
                "commerceBlockers": commerce_readiness(website),
                "registrationEnabled": public_registration_policy(context.hostname)["registrationEnabled"],
                "smtpConfigurationValid": provider_ready(), "smtpDeliveryValidated": False,
                "r2ConfigurationPresent": all(bool(getattr(settings, key, "")) for key in required_storage) and bool(getattr(settings, "R2_ENDPOINT_URL", "") or getattr(settings, "R2_ACCOUNT_ID", "")),
                "r2NetworkTested": False, "writes": False,
            }
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
