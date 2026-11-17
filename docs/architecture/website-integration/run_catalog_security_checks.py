"""Run catalog regression in a disposable local PostgreSQL database.

Usage: python run_catalog_security_checks.py --run-isolated REPOSITORY REPORT [TEST_LABEL ...]
REPOSITORY can be the current backend or an explicitly prepared baseline snapshot.
"""
import contextlib
import json
import os
from pathlib import Path
import sys

if len(sys.argv) < 4 or sys.argv[1] != "--run-isolated":
    raise SystemExit(__doc__)

source = Path(__file__).resolve().parents[3]
repository, report = Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
environment = source / ".env"
if environment.exists():
    for line in environment.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            if key.strip() in ("DJANGO_DB_USER", "DJANGO_DB_PASSWORD", "DJANGO_DB_HOST", "DJANGO_DB_PORT"):
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
if os.environ.get("DJANGO_DB_HOST", "localhost") not in ("localhost", "127.0.0.1"):
    raise SystemExit("This runner requires an explicitly local PostgreSQL server.")

os.chdir(repository)
sys.path.insert(0, str(repository))
os.environ.update(
    DJANGO_SETTINGS_MODULE="config.settings",
    DJANGO_DB_ENGINE="django.db.backends.postgresql",
    DJANGO_DB_NAME="apudig_catalog_p0_tests",
    JWT_SECRET_KEY="catalog-p0-regression-only-secret-at-least-32-characters",
)
import django

django.setup()
from django.conf import settings
from django.db import connection
from django.test.runner import DiscoverRunner

settings.STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
settings.DATABASES["default"].setdefault("TEST", {})["NAME"] = "test_apudig_catalog_p0_tests"


class EvidenceRunner(DiscoverRunner):
    def run_checks(self, databases):
        super().run_checks(databases)
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_setting('server_version')")
            database, version = cursor.fetchone()
        if database != "test_apudig_catalog_p0_tests":
            raise RuntimeError("Refusing to run tests outside the isolated database")
        self.database = {"engine": connection.vendor, "name": database, "version": version}

    def suite_result(self, suite, result, **kwargs):
        report.write_text(json.dumps({
            "database": self.database,
            "total": result.testsRun,
            "failures": [case.id() for case, _ in result.failures],
            "errors": [case.id() for case, _ in result.errors],
        }, indent=2), encoding="utf-8")
        return super().suite_result(suite, result, **kwargs)


with report.with_suffix(".log").open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
    failures = EvidenceRunner(verbosity=1, interactive=False).run_tests(sys.argv[4:] or ["apps"])
print(report.name, "completed; failures/errors:", failures)
raise SystemExit(bool(failures))
