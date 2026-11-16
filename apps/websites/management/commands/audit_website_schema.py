import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.migrations.exceptions import InconsistentMigrationHistory

from apps.websites.schema_audit import audit_website_schema


class Command(BaseCommand):
    help = "Compare Website tables, indexes and constraints with applied migrations (read only)."

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default", choices=tuple(connections))

    def handle(self, *args, **options):
        try:
            report = audit_website_schema(connections[options["database"]])
        except InconsistentMigrationHistory as exc:
            raise CommandError("Historial de migraciones inconsistente; conciliar sin --fake.") from exc
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["compatible"]:
            raise CommandError("Esquema Website divergente; no aplicar migraciones automáticamente.")
