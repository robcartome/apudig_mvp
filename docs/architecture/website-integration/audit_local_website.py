"""Read-only local Website audit; never print storage credentials or connection strings."""
import argparse
import json
import os
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--final", action="store_true")
parser.add_argument("--report", help="JSON filename in the architecture evidence directory")
arguments = parser.parse_args()
if arguments.report and (Path(arguments.report).name != arguments.report or not arguments.report.endswith(".json")):
    parser.error("--report must be a JSON filename without directories")

repository = Path(__file__).resolve().parents[3]
os.chdir(repository)
sys.path.insert(0, str(repository))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.conf import settings
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from apps.websites.models import WebsiteDomain, WebsiteProduct, WebsiteMedia, WebsiteCatalogSettings

if connection.vendor != "postgresql" or connection.settings_dict["HOST"] not in ("localhost", "127.0.0.1"):
    raise SystemExit("This audit only supports the configured local PostgreSQL database")
with transaction.atomic():
    with connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute("SELECT current_database(), current_setting('server_version')")
        database, version = cursor.fetchone()
    executor = MigrationExecutor(connection)
    executor.loader.check_consistent_history(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    domain = WebsiteDomain.objects.select_related("website__company", "website__published_revision").filter(hostname="demo.localhost").first()
    site = domain.website if domain else None
    policy = WebsiteCatalogSettings.objects.defer("commerce_enabled").filter(website=site).first() if site else None
    storage_keys = ("R2_ENDPOINT_URL", "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME", "R2_PUBLIC_BASE_URL")
    result = {
        "checkedAt": timezone.now().isoformat(),
        "database": {"engine": connection.vendor, "name": database, "version": version, "transaction": "READ ONLY"},
        "migrations": {"consistent": True, "pending": [f"{migration.app_label}.{migration.name}" for migration, _ in plan]},
        "domain": None if not domain else {"hostname": domain.hostname, "status": domain.status, "verified": domain.verified_at is not None, "websiteStatus": site.status, "companyActive": site.company.is_active, "hasPublishedRevision": site.published_revision_id is not None, "editorialRevision": site.editorial_revision},
        "catalog": None if not site else {"links": WebsiteProduct.objects.filter(website=site).count(), "published": WebsiteProduct.objects.filter(website=site, is_published=True, product__active=True, product__company_id=site.company_id).count(), "hasSettings": policy is not None, "hasDefaultPriceList": bool(policy and policy.default_price_list_id), "authorizedWarehouses": policy.warehouses.count() if policy else 0},
        "media": None if not site else {"activeRecords": WebsiteMedia.objects.filter(website=site, is_deleted=False).count(), "hasPersistentPrefix": bool(site.storage_prefix)},
        "storageConfigurationPresent": {key: bool(getattr(settings, key, "")) for key in storage_keys},
        "storageNetworkAccess": False,
        "habitualDatabaseWrites": False,
    }
filename = arguments.report or ("b4c4-local-environment-final.json" if arguments.final else "b4c4-local-environment.json")
report = repository / "docs/architecture/website-integration" / filename
report.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
