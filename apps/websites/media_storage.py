import hashlib
import uuid

from django.conf import settings

from apps.inventory.product_image_storage import (
    ProductImageStorageError,
    inspect_product_image,
    upload_processed_image,
)

from .models import WebsiteMedia


def _checksum(uploaded_file):
    digest = hashlib.sha256()
    uploaded_file.seek(0)
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()


def create_website_media(*, website, uploaded_file, kind, alt_text, actor):
    if uploaded_file.size > settings.PRODUCT_IMAGE_MAX_SIZE:
        raise ProductImageStorageError("La imagen supera el tamaño máximo permitido.")
    width, height, _ = inspect_product_image(uploaded_file)
    checksum = _checksum(uploaded_file)
    existing = WebsiteMedia.objects.filter(
        website=website, checksum=checksum, is_deleted=False
    ).first()
    if existing:
        return existing, False

    media_id = uuid.uuid4()
    base_key = f"websites/{website.pk}/media/{media_id}"
    uploaded = upload_processed_image(
        f"{base_key}.webp", f"{base_key}-thumbnail.webp", uploaded_file
    )
    media = WebsiteMedia.objects.create(
        id=media_id,
        website=website,
        kind=kind,
        storage_key=uploaded.image_key,
        thumbnail_key=uploaded.thumbnail_key,
        original_name=(uploaded_file.name or "imagen")[:255],
        alt_text=alt_text,
        mime_type="image/webp",
        size=uploaded_file.size,
        width=width,
        height=height,
        checksum=checksum,
        created_by=actor,
    )
    return media, True
