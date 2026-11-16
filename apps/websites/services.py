"""Editorial aggregate operations; every writer locks Website before child rows."""

import uuid
from copy import deepcopy

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .documents import normalize_document
from .editorial_adapter import home_page, read_draft, write_draft
from .errors import WebsiteError, invalid_document
from .models import Website, WebsiteDraftMedia, WebsiteMedia, WebsitePageRevision, WebsiteProduct, WebsiteRevisionMedia
from .permissions import require_website_permission, website_capabilities
from .selectors import get_company_website


def locked_website(*, user, company_id, website_id, store_id=None, permission="view"):
    get_company_website(user=user, company_id=company_id, store_id=store_id, website_id=website_id)
    website = Website.objects.select_for_update().get(pk=website_id, company_id=company_id)
    require_website_permission(user, company_id, permission, store_id)
    return website


def check_revision(website, expected_revision):
    if type(expected_revision) is not int or expected_revision < 0:
        raise WebsiteError("Se requiere una revisión válida.")
    if website.editorial_revision != expected_revision:
        raise WebsiteError("El contenido cambió. Recarga antes de continuar.", code="REVISION_CONFLICT", status=412)


def image_fields(document):
    yield "identity.logoUrl", document["identity"], "logoUrl", "identity.logoUrl"
    for index, item in enumerate(document["banners"]):
        for key in ("imageUrl", "mobileImageUrl"):
            yield f"banners.{item['id']}.{key}", item, key, f"banners.{index}.{key}"
    for index, item in enumerate(document["announcements"]["items"]):
        yield f"announcements.items.{item['id']}.imageUrl", item, "imageUrl", f"announcements.items.{index}.imageUrl"


def bind_media(website, document, references=None):
    document = deepcopy(document)
    if references is None:
        references = {}
    if not isinstance(references, dict) or len(references) > 33:
        raise invalid_document({"mediaReferences": "Mapa de medios no válido."})
    fields = list(image_fields(document))
    allowed_paths = {path for path, _, _, _ in fields}
    if set(references) - allowed_paths:
        raise invalid_document({"mediaReferences": "Referencia a un campo inexistente."})
    media = list(WebsiteMedia.objects.filter(website=website, is_deleted=False))
    by_id = {str(item.id): item for item in media}
    by_url = {item.url: item for item in media if item.url}
    resolved = {}
    errors = {}
    for path, item, key, error_path in fields:
        if path not in references and not item[key]:
            continue
        asset = by_id.get(str(references[path])) if path in references else by_url.get(item[key])
        if asset is None or not asset.url or not asset.storage_key.startswith(f"websites/{website.pk}/media/"):
            errors[error_path] = "Selecciona un medio activo del mismo website."
            continue
        item[key] = asset.url
        resolved[path] = str(asset.id)
    if errors:
        raise invalid_document(errors)
    return normalize_document(document), resolved


def validate_products(website, document):
    groups = [("specials.productIds", document["specials"]["productIds"])]
    groups += [(f"promotions.{index}.productIds", campaign["productIds"]) for index, campaign in enumerate(document["promotions"])]
    selected = set()
    errors = {}
    for path, values in groups:
        for value in values:
            try:
                if str(uuid.UUID(value)) != value:
                    raise ValueError
                selected.add(value)
            except (ValueError, TypeError, AttributeError):
                errors[path] = "Usa identificadores UUID canónicos; no se aceptan productos demo."
    if errors:
        raise invalid_document(errors)
    if not selected:
        return
    available = set(str(value) for value in WebsiteProduct.objects.filter(
        website=website, is_published=True, product__active=True,
        product__company_id=website.company_id, product_id__in=selected,
    ).values_list("product_id", flat=True))
    for path, values in groups:
        if set(values) - available:
            errors[path] = "Los productos deben estar publicados en este website."
    if errors:
        raise invalid_document(errors)


def revision_document(revision):
    snapshot = revision.snapshot
    if not isinstance(snapshot, dict) or snapshot.get("schemaVersion") != 3 or "document" not in snapshot:
        raise WebsiteError("La revisión histórica requiere una conversión explícita.", code="LEGACY_CONTENT_REQUIRES_MIGRATION", status=409)
    return normalize_document(snapshot["document"])


def editor_record(website, user, store_id=None):
    _, capabilities = website_capabilities(user, website.company_id, store_id)
    events = WebsitePageRevision.objects.filter(page__website=website, page__page_type="HOME").order_by("-created_at", "-version")[:20]
    return {
        "schemaVersion": 3, "companyId": str(website.company_id), "websiteId": str(website.pk),
        "revision": website.editorial_revision, "draft": read_draft(website),
        "published": revision_document(website.published_revision) if website.published_revision_id else None,
        "updatedAt": website.updated_at if website.editorial_revision else None,
        "publishedAt": website.published_at,
        "events": [{"action": item.operation.lower(), "at": item.created_at, "revision": item.editorial_revision} for item in events],
        "capabilities": capabilities,
    }


def create_revision(website, page, document, references, actor, operation, source_revision=None):
    version = (page.revisions.aggregate(last=Max("version"))["last"] or 0) + 1
    revision = WebsitePageRevision.objects.create(
        page=page, version=version, operation=operation, editorial_revision=website.editorial_revision,
        source_revision=source_revision, created_by=actor,
        snapshot={"schemaVersion": 3, "templateKey": website.template_key, "templateSchemaVersion": website.template_schema_version, "document": deepcopy(document), "mediaReferences": deepcopy(references)},
    )
    WebsiteRevisionMedia.objects.bulk_create([
        WebsiteRevisionMedia(revision=revision, media_id=media_id) for media_id in set(references.values())
    ])
    return revision


@transaction.atomic
def load_editor(*, user, company_id, website_id, store_id=None):
    website = locked_website(user=user, company_id=company_id, store_id=store_id, website_id=website_id)
    return editor_record(website, user, store_id)


@transaction.atomic
def save_draft(*, user, company_id, website_id, document, expected_revision, media_references=None, store_id=None):
    website = locked_website(user=user, company_id=company_id, store_id=store_id, website_id=website_id, permission="edit")
    check_revision(website, expected_revision)
    read_draft(website)  # Do not silently overwrite unconverted historical blocks.
    document, references = bind_media(website, normalize_document(document), media_references)
    validate_products(website, document)
    website.editorial_revision += 1
    website.updated_by = user
    website.save(update_fields=("editorial_revision", "updated_by", "updated_at"))
    page = write_draft(website, document, user, references)
    WebsiteDraftMedia.objects.filter(website=website).delete()
    WebsiteDraftMedia.objects.bulk_create([WebsiteDraftMedia(website=website, path=path, media_id=value) for path, value in references.items()])
    create_revision(website, page, document, references, user, "SAVE")
    return editor_record(website, user, store_id)


@transaction.atomic
def publish_website(*, user, company_id, website_id, expected_revision, store_id=None):
    website = locked_website(user=user, company_id=company_id, store_id=store_id, website_id=website_id, permission="publish")
    check_revision(website, expected_revision)
    if website.status == Website.Status.SUSPENDED:
        raise WebsiteError("El website está suspendido; publicar no lo reactiva.", code="WEBSITE_SUSPENDED", status=409)
    page = home_page(website)
    if page is None or not page.revisions.filter(operation__in=("SAVE", "RESTORE")).exists():
        raise invalid_document({"document": "Guarda un borrador antes de publicar."})
    references = dict(website.draft_media.values_list("path", "media_id"))
    document, references = bind_media(website, read_draft(website), references)
    validate_products(website, document)
    website.editorial_revision += 1
    revision = create_revision(website, page, document, references, user, "PUBLISH")
    now = timezone.now()
    page.status = "PUBLISHED"
    page.published_version = revision.version
    page.published_at = now
    page.draft_version = website.editorial_revision
    page.updated_by = user
    page.save()
    website.published_revision = revision
    website.published_at = now
    website.status = "PUBLISHED"
    website.updated_by = user
    website.save(update_fields=("editorial_revision", "published_revision", "published_at", "status", "updated_by", "updated_at"))
    return editor_record(website, user, store_id)


@transaction.atomic
def restore_revision(*, user, company_id, website_id, revision_id, expected_revision, store_id=None):
    website = locked_website(user=user, company_id=company_id, store_id=store_id, website_id=website_id, permission="edit")
    check_revision(website, expected_revision)
    revision = WebsitePageRevision.objects.get(pk=revision_id, page__website=website, page__page_type="HOME")
    document, references = bind_media(website, revision_document(revision), revision.snapshot.get("mediaReferences", {}))
    validate_products(website, document)
    website.editorial_revision += 1
    website.updated_by = user
    website.save(update_fields=("editorial_revision", "updated_by", "updated_at"))
    page = write_draft(website, document, user, references)
    WebsiteDraftMedia.objects.filter(website=website).delete()
    WebsiteDraftMedia.objects.bulk_create([WebsiteDraftMedia(website=website, path=path, media_id=value) for path, value in references.items()])
    create_revision(website, page, document, references, user, "RESTORE", revision)
    return editor_record(website, user, store_id)
