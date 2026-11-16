"""Disposable PostgreSQL runner; never loads the habitual database configuration."""
import contextlib
import json
import os
from pathlib import Path
import sys

repo, report = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
os.chdir(repo)
sys.path.insert(0, str(repo))
os.environ.update(DJANGO_SETTINGS_MODULE="config.settings", DJANGO_DB_ENGINE="django.db.backends.postgresql", DJANGO_DB_NAME="apudig_b3_integration", DJANGO_DB_HOST="127.0.0.1", DJANGO_DB_PORT="55439", DJANGO_DB_USER="apudig_b3", DJANGO_DB_PASSWORD="", JWT_SECRET_KEY="b3-isolated-testing-only-secret-at-least-32-bytes", R2_ACCESS_KEY_ID="", R2_SECRET_ACCESS_KEY="")
import django
django.setup()
from django.conf import settings
from django.test.runner import DiscoverRunner

settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
settings.STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}

class EvidenceRunner(DiscoverRunner):
    def suite_result(self, suite, result, **kwargs):
        report.write_text(json.dumps({"total": result.testsRun, "failures": [case.id() for case, _ in result.failures], "errors": [case.id() for case, _ in result.errors]}, indent=2), encoding="utf-8")
        return super().suite_result(suite, result, **kwargs)

with report.with_suffix(".log").open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
    failed = EvidenceRunner(verbosity=1, interactive=False).run_tests(sys.argv[3:] or ["apps"])
print(report.name, "completed; failures/errors:", failed)
