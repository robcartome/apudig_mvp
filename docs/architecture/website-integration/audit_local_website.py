"""Read-only local Website audit; never print storage credentials or connection strings."""
import json
import os
from pathlib import Path
import sys

if sys.argv[1:] not in ([], ["--final"]):
    raise SystemExit("Usage: audit_local_website.py [--final]")

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
    policy = WebsiteCatalogSettings.objects.filter(website=site).first() if site else None
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
filename = "b4c4-local-environment-final.json" if sys.argv[1:] else "b4c4-local-environment.json"
report = repository / "docs/architecture/website-integration" / filename
report.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
