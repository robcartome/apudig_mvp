import json
import os
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo))
os.environ.update(DJANGO_SETTINGS_MODULE="config.settings", DJANGO_DB_ENGINE="django.db.backends.postgresql", DJANGO_DB_NAME="apudig_b3_integration", DJANGO_DB_HOST="127.0.0.1", DJANGO_DB_PORT="55439", DJANGO_DB_USER="apudig_b3", DJANGO_DB_PASSWORD="", JWT_SECRET_KEY="b3-isolated-testing-only-secret-at-least-32-bytes")
import django
django.setup()
from django.conf import settings
from django.utils import timezone
from apps.companies.models import Company, UserCompanyAccess
from apps.users.models import User, Role, UserRole, Permission, RolePermission
from apps.websites.models import Website, WebsiteDomain

assert settings.DATABASES["default"]["NAME"] == "apudig_b3_integration"
result = {}
for index, label in enumerate(("A", "B"), 1):
    company, _ = Company.objects.get_or_create(ruc=f"2099911130{index}", defaults={"name": f"Integration company {label}"})
    website, _ = Website.objects.get_or_create(company=company, defaults={"name": f"Integration Website {label}"})
    domain, _ = WebsiteDomain.objects.get_or_create(hostname=f"{label.lower()}.b3.localhost", defaults={"website": website, "status": "ACTIVE", "verified_at": timezone.now(), "is_primary": True})
    user, _ = User.objects.get_or_create(email=f"b3-{label.lower()}@example.test")
    user.set_password("Integration-B3-only-2026")
    user.save()
    UserCompanyAccess.objects.get_or_create(user=user, company=company)
    role, _ = Role.objects.get_or_create(name=f"B3 test editor {label}")
    UserRole.objects.get_or_create(user=user, company=company, role=role)
    for code in ("read.website", "manage.website", "publish.website", "manage.website.media"):
        RolePermission.objects.get_or_create(role=role, permission=Permission.objects.get(code=code))
    result[label] = {"companyId": str(company.pk), "websiteId": str(website.pk), "hostname": domain.hostname, "email": user.email}
fixture_path = repo.parent / ".tools/b3-fixture.json"
fixture_path.parent.mkdir(exist_ok=True)
fixture_path.write_text(json.dumps(result), encoding="utf-8")
print("Two isolated tenants and test-only users provisioned; no publication or DNS changes.")
