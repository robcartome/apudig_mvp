"""Website-owned uploads reuse the ERP image decoder and optimizer, not product keys."""

import hashlib
import logging
import uuid
from io import BytesIO
from PIL import Image

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from apps.core.models import AuditLog
from apps.inventory import product_image_storage as images

from .errors import WebsiteError, invalid_document
from .documents import is_plain_text, safe_image
from .editorial_adapter import EDITORIAL_BLOCKS
from .models import Website, WebsiteMedia, WebsitePageRevision, WebsiteSection, WebsiteSettings
from .permissions import require_website_permission
from .selectors import get_company_website


logger = logging.getLogger(__name__)


def create_r2_client():
    return images._get_r2_client()


def delete_uploaded_objects(keys):
    if not keys:
        return
    try:
        client = create_r2_client()
        for key in keys:
            client.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
    except Exception:
        logger.error("Website upload cleanup failed; reconcile unreferenced object keys: %s", keys)


def upload_media(*, user, company_id, website_id, uploaded_file, kind="IMAGE", alt_text="", store_id=None):
    get_company_website(user=user, company_id=company_id, store_id=store_id, website_id=website_id, permission="mediaUpload")
    if kind not in WebsiteMedia.Kind.values:
        raise invalid_document({"kind": "Tipo de medio no válido."})
    if not is_plain_text(alt_text, 180):
        raise invalid_document({"altText": "Usa texto plano de hasta 180 caracteres."})
    public_url = images.build_public_url("websites/validation.webp")
    if not public_url.startswith("https://") or not safe_image(public_url):
        raise WebsiteError("La URL pública de medios no está configurada.", code="MEDIA_UNAVAILABLE", status=503)
    name = (uploaded_file.name or "image").replace("\\", "/").rsplit("/", 1)[-1]
    if name.rsplit(".", 1)[-1].lower() not in ("png", "jpg", "jpeg", "webp"):
        raise WebsiteError("Formato de archivo no permitido.", code="UNSUPPORTED_MEDIA_TYPE", status=415)
    uploaded_file.seek(0)
    data = uploaded_file.read(settings.PRODUCT_IMAGE_MAX_SIZE + 1)
    if len(data) > settings.PRODUCT_IMAGE_MAX_SIZE:
        raise WebsiteError("La imagen supera el límite de tamaño.", code="PAYLOAD_TOO_LARGE", status=413)
    source = BytesIO(data)
    try:
        width, height, _ = images.inspect_product_image(source)
        image_body = images.optimize_product_image(source)
        thumbnail_body = images.optimize_product_image(source, max_dimension=settings.PRODUCT_IMAGE_THUMBNAIL_DIMENSION, quality=settings.PRODUCT_IMAGE_THUMBNAIL_QUALITY)
        with Image.open(BytesIO(image_body)) as processed:
            width, height = processed.size
    except images.ProductImageStorageError as exc:
        raise invalid_document({"file": str(exc)}) from exc
    checksum = hashlib.sha256(data).hexdigest()
    uploaded_keys = []
    try:
        with transaction.atomic(durable=True):
            website = Website.objects.select_for_update().get(pk=website_id, company_id=company_id)
            require_website_permission(user, company_id, "mediaUpload", store_id)
            existing = WebsiteMedia.objects.filter(website=website, checksum=checksum, is_deleted=False).first()
            if existing:
                return existing, False
            media_id = uuid.uuid4()
            key = f"websites/{website.pk}/media/{media_id}"
            try:
                client = create_r2_client()
                for object_key, body in ((key + ".webp", image_body), (key + "-thumbnail.webp", thumbnail_body)):
                    # Include the attempted key: a timed-out PUT may have succeeded.
                    uploaded_keys.append(object_key)
                    client.put_object(Bucket=settings.R2_BUCKET_NAME, Key=object_key, Body=body, ContentType="image/webp", CacheControl="public, max-age=31536000, immutable")
            except Exception as exc:
                raise WebsiteError("No se pudo almacenar la imagen.", code="MEDIA_UNAVAILABLE", status=503) from exc
            media = WebsiteMedia.objects.create(id=media_id, website=website, kind=kind, storage_key=key + ".webp", thumbnail_key=key + "-thumbnail.webp", original_name=name[:255], alt_text=alt_text, mime_type="image/webp", size=len(data), width=width, height=height, checksum=checksum, created_by=user)
            AuditLog.objects.create(user=user, action="WEBSITE_MEDIA_UPLOAD", entity="Website", entity_id=str(website.pk), meta_data={"mediaId": str(media.id)})
        return media, True
    except Exception:
        delete_uploaded_objects(uploaded_keys)
        raise


@transaction.atomic
def deactivate_media(*, user, company_id, website_id, media_id, store_id=None):
    get_company_website(user=user, company_id=company_id, store_id=store_id, website_id=website_id)
    website = Website.objects.select_for_update().get(pk=website_id, company_id=company_id)
    require_website_permission(user, company_id, "mediaUpload", store_id)
    media = WebsiteMedia.objects.get(pk=media_id, website=website, is_deleted=False)
    legacy_history = WebsitePageRevision.objects.filter(page__website=website, operation="BASELINE").exists()
    legacy_blocks = WebsiteSection.objects.filter(page__website=website).exclude(section_type__in=EDITORIAL_BLOCKS).exists()
    legacy_theme = WebsiteSettings.objects.filter(website=website).filter(Q(logo_url=media.url) | Q(favicon_url=media.url)).exists()
    if media.draft_references.exists() or media.revision_references.exists() or media.logo_for_settings.exists() or media.favicon_for_settings.exists() or legacy_history or legacy_blocks or legacy_theme:
        raise WebsiteError("La imagen está referenciada por contenido o historial retenido.", code="MEDIA_IN_USE", status=409)
    media.is_deleted = True
    media.save(update_fields=("is_deleted", "updated_at"))
    AuditLog.objects.create(user=user, action="WEBSITE_MEDIA_DELETE", entity="Website", entity_id=str(website.pk), meta_data={"mediaId": str(media.id)})
