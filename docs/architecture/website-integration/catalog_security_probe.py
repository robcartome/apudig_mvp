"""Opt-in diagnosis using synthetic PostgreSQL fixtures, never the habitual DB.

Run from backend root: .venv/Scripts/python.exe path/to/this.py --run-isolated
Successful execution means the diagnosis completed, NOT that security passed.
Historical baseline diagnostic: its insecure expectations predate the P0 patch.
Use run_catalog_security_checks.py and test_catalog_security for acceptance.
"""
import json
import os
from pathlib import Path
import sys
import unittest

if __name__ != "__main__" or sys.argv[1:] != ["--run-isolated"]:
    raise SystemExit("Use --run-isolated to run the synthetic PostgreSQL diagnosis.")

root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root))
os.environ.update(DJANGO_SETTINGS_MODULE="config.settings", DJANGO_DB_ENGINE="django.db.backends.postgresql", DJANGO_DB_NAME="apudig_catalog_security_audit", JWT_SECRET_KEY="catalog-security-probe-only-secret-at-least-32-characters")

import django
django.setup()
from django.conf import settings
from django.test import TestCase
from django.test.runner import DiscoverRunner
from apps.api.v1.auth.tokens import build_token
from apps.companies.models import Company, Store, UserCompanyAccess
from apps.inventory.models import Product, Unit, PriceList, ProductPrice, Warehouse, StockByWarehouse
from apps.users.models import User

if settings.DATABASES["default"]["HOST"] not in ("localhost", "127.0.0.1"):
    raise SystemExit("This diagnosis requires the explicitly local PostgreSQL server.")
settings.STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
findings = {}


class LegacyCatalogDiagnosis(TestCase):
    def test_record_isolation_and_exposure(self):
        a = Company.objects.create(name="Synthetic A", ruc="20999000101")
        b = Company.objects.create(name="Synthetic B", ruc="20999000102")
        unit = Unit.objects.create(code="AUD", name="Audit unit")
        first = Product.objects.create(company=a, name="Synthetic product A", sku="AUD-A", unit=unit, price_sale="10.00", price_purchase="4.00")
        second = Product.objects.create(company=b, name="Synthetic product B", sku="AUD-B", unit=unit, price_sale="20.00", price_purchase="8.00")
        price_list = PriceList.objects.create(company=a, name="Synthetic internal list")
        ProductPrice.objects.create(product=first, price_list=price_list, amount="9.00")
        store = Store.objects.create(company=a, name="Synthetic store")
        warehouse = Warehouse.objects.create(store=store, name="Synthetic internal warehouse")
        StockByWarehouse.objects.create(product=first, warehouse=warehouse, quantity="7.000")

        response = self.client.get("/api/v1/catalog/products/")
        self.assertEqual(response.status_code, 200)  # Assert fixture/endpoint viability, not security.
        ids = {item["id"] for item in response.json()["results"]}
        findings["anonymousGlobalProducts"] = str(first.pk) in ids and str(second.pk) in ids
        detail = self.client.get(f"/api/v1/catalog/products/{first.pk}/detail/").json()
        findings["anonymousInternalPriceLists"] = bool(detail.get("price_list"))
        findings["anonymousWarehouseDetails"] = bool(detail.get("stock_by_warehouse"))

        user = User.objects.create_user(email="synthetic-audit@example.test")
        membership = UserCompanyAccess.objects.create(user=user, company=a)
        token = build_token({"sub": str(user.pk), "type": "access", "company_id": str(a.pk)}, settings.JWT_ACCESS_TTL)
        membership.delete()
        private = self.client.get(f"/api/v1/catalog/private/products/{first.pk}/detail/", HTTP_AUTHORIZATION=f"Bearer {token}")
        findings["revokedMembershipStillReadsCosts"] = private.status_code == 200 and "price_purchase" in private.json()
        a.is_active = False
        a.save()
        inactive = self.client.get(f"/api/v1/catalog/private/products/{first.pk}/detail/", HTTP_AUTHORIZATION=f"Bearer {token}")
        findings["inactiveCompanyStillReadable"] = inactive.status_code == 200


class DiagnosticRunner(DiscoverRunner):
    def build_suite(self, *args, **kwargs):
        return unittest.defaultTestLoader.loadTestsFromTestCase(LegacyCatalogDiagnosis)


errors = DiagnosticRunner(verbosity=0, interactive=False).run_tests([])
report = {"date": "2026-11-16", "database": "test_apudig_catalog_security_audit", "engine": "PostgreSQL", "syntheticFixturesOnly": True, "diagnosticErrors": errors, "observedSecurityViolations": findings, "securityAccepted": False}
Path(__file__).with_name("catalog-security-probe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(bool(errors))
