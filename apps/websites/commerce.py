"""One persistent opt-in; readiness never enables commerce by itself."""
import re

from django.db import connection

from .errors import WebsiteError
from .models import Website, WebsiteCatalogSettings, WebsiteDomain, WebsiteRegistrationPolicy


def commerce_schema_ready():
    with connection.cursor() as cursor:
        columns = connection.introspection.get_table_description(cursor, WebsiteCatalogSettings._meta.db_table)
    return any(column.name == "commerce_enabled" for column in columns)


def commerce_readiness(website):
    blockers = []

    def require(condition, code, message):
        if not condition:
            blockers.append({"code": code, "message": message})

    tables = set(connection.introspection.table_names())
    required = {"website_commercial_sessions", "website_commercial_order_requests", "website_privacy_notices", "website_registration_policies", "website_commercial_consents"}
    require(required.issubset(tables) and commerce_schema_ready(), "SCHEMA_PENDING", "Aplica y verifica las migraciones comerciales en el entorno autorizado.")
    require(website.company.is_active and website.status == "PUBLISHED" and website.published_at and website.published_revision_id, "WEBSITE_UNPUBLISHED", "Publica el Website de una empresa activa.")
    require(WebsiteDomain.objects.filter(website=website, status="ACTIVE", verified_at__isnull=False).exists(), "DOMAIN_UNAVAILABLE", "Se necesita un dominio activo y verificado.")
    revision = website.published_revision
    valid_revision = revision and isinstance(revision.snapshot, dict) and revision.operation == "PUBLISH" and revision.page.website_id == website.pk and revision.page.page_type == "HOME" and revision.page.status == "PUBLISHED" and revision.page.published_version == revision.version and revision.snapshot.get("schemaVersion") == 3 and revision.snapshot.get("templateKey") == "ecommerce"
    require(valid_revision, "REVISION_UNAVAILABLE", "Publica una revisión editorial válida del Website.")
    document = revision.snapshot.get("document", {}) if valid_revision else {}
    phone = document.get("contact", {}).get("whatsapp", "")
    require(isinstance(phone, str) and re.fullmatch(r"[0-9]{8,15}", phone), "CONTACT_UNAVAILABLE", "Publica un WhatsApp empresarial válido.")
    if "website_registration_policies" in tables:
        policy = WebsiteRegistrationPolicy.objects.select_related("notice").filter(website=website, notice__website=website).first()
        require(policy and policy.notice.text.strip() and policy.notice.version.strip() and policy.notice.pending_retention_days > 0, "PRIVACY_UNAVAILABLE", "Configura un aviso aprobado, versionado y con conservación definida.")
    from .catalog.selectors import catalog_offers, configured_warehouses
    configuration = WebsiteCatalogSettings.objects.defer("commerce_enabled").filter(website=website).first()
    warehouses = configured_warehouses(website, configuration)
    require(warehouses.exists(), "WAREHOUSES_UNAVAILABLE", "Autoriza los almacenes de disponibilidad del Website.")
    offers = catalog_offers(website, configuration=configuration)
    require(offers.filter(offer_price__isnull=False).exists(), "PUBLIC_OFFER_UNAVAILABLE", "Publica al menos un producto con precio de una lista autorizada en la moneda del Website.")
    return blockers


def require_commerce_ready(website):
    blockers = commerce_readiness(website)
    if blockers:
        raise WebsiteError("Completa la preparación comercial antes de habilitar solicitudes.", code="COMMERCE_NOT_READY", status=409, fields={item["code"]: item["message"] for item in blockers})


def commerce_enabled(website_id):
    # The additive migration may precede a rolling deployment. Old schemas
    # remain readable with commerce closed; never auto-migrate on a request.
    if not commerce_schema_ready() or not WebsiteCatalogSettings.objects.filter(website_id=website_id, commerce_enabled=True).exists():
        return False
    website = Website.objects.select_related("company", "published_revision__page").get(pk=website_id)
    return not commerce_readiness(website)
