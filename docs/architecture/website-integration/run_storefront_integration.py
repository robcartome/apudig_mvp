"""Local isolated HTTP environment. No habitual DB writes, no external media.

From backend: python path/to/run_storefront_integration.py --serve-isolated
Writes synthetic fixture context under workspace .tools; never print tokens.
Stdin commands: {"operation":"price","amount":"12.00"},
{"operation":"stock","quantity":"1.00"}, {"operation":"stop"}.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

simulate_email = sys.argv[1:] == ["--serve-isolated", "--simulate-email"]
if sys.argv[1:] != ["--serve-isolated"] and not simulate_email:
    raise SystemExit(__doc__)
repository = Path(__file__).resolve().parents[3]
workspace = repository.parent
os.chdir(repository)
sys.path.insert(0, str(repository))
os.environ.update(
    DJANGO_SETTINGS_MODULE="config.settings", DJANGO_DB_ENGINE="django.db.backends.postgresql",
    DJANGO_DB_NAME="apudig_b4c_http_source", JWT_SECRET_KEY="b4c-isolated-http-only-secret-at-least-32-characters",
    R2_ACCESS_KEY_ID="", R2_SECRET_ACCESS_KEY="", DJANGO_DEBUG="1",
    WEBSITE_REGISTRATION_ENABLED="0", WEBSITE_EMAIL_BACKEND="disabled",
)
if simulate_email:
    os.environ.update(WEBSITE_REGISTRATION_ENABLED="1", WEBSITE_EMAIL_BACKEND="smtp", WEBSITE_SMTP_HOST="smtp.integration.invalid", WEBSITE_EMAIL_FROM="noreply@integration.invalid", WEBSITE_SMTP_USER="synthetic", WEBSITE_SMTP_PASSWORD="synthetic")
import django
django.setup()
from django.conf import settings
from django.db import connection
from django.test import TestCase
from django.test.runner import DiscoverRunner
from django.utils import timezone
from apps.api.v1.auth.tokens import build_token
from apps.companies.models import Company, UserCompanyAccess
from apps.users.models import UserRole
from apps.inventory.models import Product, ProductPrice
from apps.websites.models import Website, WebsiteCatalogSettings, WebsiteDomain, WebsitePage, WebsitePageRevision, WebsiteProduct
from apps.websites.tests.test_catalog import CommercialCatalogFixture
from apps.websites.tests.test_editorial import editorial_fixture

if connection.settings_dict["HOST"] not in ("localhost", "127.0.0.1"):
    raise SystemExit("Only explicitly local PostgreSQL is supported")
with socket.socket() as port_check:
    port_check.bind(("127.0.0.1", 8770))
settings.DATABASES["default"].setdefault("TEST", {})["NAME"] = "test_apudig_b4c_http"
settings.STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
runner = DiscoverRunner(interactive=False, verbosity=0)
databases = runner.setup_databases()


def assert_isolated():
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        if cursor.fetchone()[0] != "test_apudig_b4c_http":
            raise RuntimeError("Refusing any fixture write outside the isolated database")


class HTTPFixture(CommercialCatalogFixture, TestCase):
    def published_site(self, company, hostname):
        hostname = "a.b4c.localhost" if company == self.a else "b.b4c.localhost"
        website = Website.objects.create(company=company, name=company.name)
        page = WebsitePage.objects.create(website=website, slug="home", title="Home", page_type="HOME", status="PUBLISHED", draft_version=1, published_version=1)
        document = editorial_fixture()
        document["identity"].update(name=company.name, shortName=company.name, primaryColor="#1166AA" if company == self.a else "#AA1166")
        document["seo"].update(title=company.name + " | Catalog", description="Published information for " + company.name)
        document["contact"]["whatsapp"] = "51900000001"
        revision = WebsitePageRevision.objects.create(page=page, version=1, operation="PUBLISH", editorial_revision=1, snapshot={"schemaVersion": 3, "templateKey": "ecommerce", "document": document})
        website.status, website.published_revision, website.editorial_revision = "PUBLISHED", revision, 1
        website.published_at = timezone.now()
        website.save()
        WebsiteDomain.objects.create(website=website, hostname=hostname, status="ACTIVE", verified_at=timezone.now())
        return website


process = None
context_path = workspace / ".tools/b4c-http-context.json"
try:
    assert_isolated()
    fixture = HTTPFixture()
    fixture.setUp()
    for index in range(25):
        product = Product.objects.create(company=fixture.a, unit=fixture.unit, category=fixture.category if index % 2 else fixture.other_category, brand=fixture.brand if index % 2 else fixture.other_brand, sku=f"HTTP-{index:02}", name=f"Public HTTP product {index:02}")
        ProductPrice.objects.create(product=product, price_list=fixture.price_list, amount=index + 1)
        WebsiteProduct.objects.create(website=fixture.site, product=product, is_published=True, is_featured=index < 3)
    zero = Product.objects.create(company=fixture.a, unit=fixture.unit, sku="ZERO", name="Authorized zero price")
    ProductPrice.objects.create(product=zero, price_list=fixture.price_list, amount=0)
    WebsiteProduct.objects.create(website=fixture.site, product=zero, is_published=True)
    ProductPrice.objects.filter(product=fixture.second).update(active=False)
    ProductPrice.objects.create(product=fixture.foreign, price_list=fixture.foreign_list, amount=120)
    WebsiteCatalogSettings.objects.create(website=fixture.foreign_site, default_price_list=fixture.foreign_list)
    WebsiteDomain.objects.create(website=fixture.site, hostname="pending.b4c.localhost")
    WebsiteDomain.objects.create(website=fixture.site, hostname="disabled.b4c.localhost", status="DISABLED")
    company = Company.objects.create(name="Unpublished HTTP Company", ruc="20999110003")
    unpublished_site = Website.objects.create(company=company, name=company.name)
    WebsiteDomain.objects.create(website=unpublished_site, hostname="unpublished.b4c.localhost", status="ACTIVE", verified_at=timezone.now())
    password = "Isolated-B4C-Only-Password-2026"
    # The same synthetic editor is a basic worker in B; company switching must
    # re-evaluate current grants rather than carry A's CMS permissions over.
    UserCompanyAccess.objects.create(user=fixture.editor, company=fixture.b)
    UserCompanyAccess.objects.create(user=fixture.admin, company=fixture.b)
    admin_role = UserRole.objects.get(user=fixture.admin, company=fixture.a, role__name="ADMIN").role
    UserRole.objects.create(user=fixture.admin, company=fixture.b, role=admin_role)
    auth = {}
    for name in ("admin", "editor", "reader", "worker", "media"):
        user = getattr(fixture, name)
        user.set_password(password)
        user.save()
        auth[name] = {"email": user.email, "password": password, "token": build_token({"sub": str(user.pk), "type": "access", "company_id": str(fixture.a.pk)}, settings.JWT_ACCESS_TTL)}
    # Commercial fixtures never send mail or confer employee memberships.
    from apps.users.models import User
    from apps.partners.models import Customer, SalesCustomerProfile
    from apps.websites.models import CommercialAccount
    from apps.websites.accounts import issue_email_challenge, verify_email_challenge
    customer_user = User.objects.create_user(email="customer@b4d1.example.test", password=password, name="Cliente comercial de prueba", phone="999111222")
    commercial_accounts = {}
    for name, user, website, verified in (
        ("customerA", customer_user, fixture.site, True),
        ("customerB", customer_user, fixture.foreign_site, True),
        ("mixedA", fixture.worker, fixture.site, True),
    ):
        customer = Customer.objects.create(company=website.company, document_type="0", legal_name=name)
        account = CommercialAccount.objects.create(company=website.company, customer=customer, user=user)
        if verified:
            secret = issue_email_challenge(user, website)
            verify_email_challenge(user, website, secret)
        SalesCustomerProfile.objects.create(customer=customer, price_list=fixture.price_list if website == fixture.site else fixture.foreign_list)
        commercial_accounts[name] = str(account.pk)
    auth["customer"] = {"email": customer_user.email, "password": password}
    context = {
        "database": "test_apudig_b4c_http", "backend": "http://127.0.0.1:8770/api/v1", "next": "http://127.0.0.1:8771",
        "hostA": "a.b4c.localhost", "hostB": "b.b4c.localhost", "websiteA": str(fixture.site.pk), "websiteB": str(fixture.foreign_site.pk),
        "productA": str(fixture.product.pk), "productB": str(fixture.foreign.pk), "zero": str(zero.pk), "nullPrice": str(fixture.second.pk),
        "publicationA": str(fixture.publication.pk), "unpublishedProduct": str(fixture.unpublished.pk),
        "categoryA": str(fixture.category.pk), "categoryOther": str(fixture.other_category.pk), "brandA": str(fixture.brand.pk), "brandOther": str(fixture.other_brand.pk),
        "priceList": str(fixture.price_list.pk), "foreignPriceList": str(fixture.foreign_list.pk), "warehouse": str(fixture.warehouse.pk),
        "auth": auth,
        "commercialAccounts": commercial_accounts, "commercialVerification": "synthetic_fixture_only_no_email_delivery",
        "emailSimulation": simulate_email,
    }
    context_path.write_text(json.dumps(context, indent=2), encoding="utf-8")
    environment = dict(os.environ, DJANGO_DB_NAME="test_apudig_b4c_http", CORS_ALLOWED_ORIGINS="http://a.b4c.localhost:8771,http://b.b4c.localhost:8771,http://localhost:8771")
    with (workspace / ".tools/b4c-django-http.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "manage.py", "runserver", "127.0.0.1:8770", "--noreload"], cwd=repository, env=environment, stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for attempt in range(100):
            try:
                urllib.request.urlopen("http://127.0.0.1:8770/api/v1/storefront/sites/a.b4c.localhost/products/", timeout=1)
                break
            except Exception:
                if process.poll() is not None:
                    raise RuntimeError("Isolated Django process failed; inspect its log")
                time.sleep(0.2)
        else:
            raise RuntimeError("Django did not become ready")
        print("READY: isolated PostgreSQL HTTP fixtures; context saved without printing credentials", flush=True)
        for line in sys.stdin:
            command = json.loads(line)
            if command["operation"] == "stop":
                break
            assert_isolated()
            if command["operation"] == "price":
                fixture.price.amount = command["amount"]
                fixture.price.save()
                print("OK: isolated ERP price updated", flush=True)
            elif command["operation"] == "stock":
                fixture.stock.quantity = command["quantity"]
                fixture.stock.save(update_fields=["quantity"])
                print("OK: isolated authorized stock updated", flush=True)
            elif command["operation"] == "prepare_commerce":
                from copy import deepcopy
                from apps.websites.registration import configure_notice, policy_for, policy_etag
                from apps.websites.catalog.services import update_configuration, commercial_etag
                previous = fixture.site.published_revision
                snapshot = deepcopy(previous.snapshot)
                snapshot["document"]["contact"]["whatsapp"] = "51900000001"
                page = previous.page
                version = max(page.draft_version, page.published_version) + 1
                page.published_version = page.draft_version = version
                page.save(update_fields=["published_version", "draft_version"])
                fixture.site.published_revision = WebsitePageRevision.objects.create(page=page, version=version, operation="PUBLISH", editorial_revision=version, snapshot=snapshot)
                fixture.site.editorial_revision = version
                fixture.site.save(update_fields=["published_revision", "editorial_revision"])
                configure_notice(user=fixture.admin, company_id=fixture.a.pk, website_id=fixture.site.pk, version="integration-v1", text="Synthetic integration notice only. Not approved legal text for a real company.", pending_retention_days=3, linking_mode="NEW_OR_REVIEW", expected=policy_etag(policy_for(fixture.site)))
                update_configuration(user=fixture.admin, company_id=fixture.a.pk, website_id=fixture.site.pk, expected=commercial_etag(fixture.site), data={"commerceEnabled": True})
                print("OK: isolated Website published/contact/privacy and explicit admin opt-in prepared", flush=True)
            elif command["operation"] == "deliver_email" and simulate_email:
                from unittest.mock import patch
                from django.core import mail
                from django.core.mail.backends.locmem import EmailBackend
                from apps.websites.registration_mail import send_queued_emails
                import re
                with patch("apps.websites.registration_mail.get_connection", return_value=EmailBackend()):
                    result = send_queued_emails()
                secret = re.search(r"#token=([A-Za-z0-9_-]+)", mail.outbox[-1].body).group(1)
                (workspace / ".tools/d5-email-proof.json").write_text(json.dumps({"token": secret, "externalAdapter": "locmem SMTP simulation only"}), encoding="utf-8")
                print("OK: external SMTP adapter simulated; private synthetic proof saved, no real delivery", flush=True)
            elif command["operation"] == "advance_registration_cooldown" and simulate_email:
                from datetime import timedelta
                from apps.websites.models import CommercialRegistration
                CommercialRegistration.objects.filter(website=fixture.site).update(created_at=timezone.now() - timedelta(minutes=2))
                print("OK: isolated registration fixture cooldown advanced", flush=True)
            else:
                print("Unknown isolated operation", flush=True)
finally:
    if process is not None:
        process.terminate()
        process.wait(timeout=15)
    context_path.unlink(missing_ok=True)
    (workspace / ".tools/d5-email-proof.json").unlink(missing_ok=True)
    runner.teardown_databases(databases)
    print("Stopped isolated HTTP environment; database and synthetic credential context removed", flush=True)
