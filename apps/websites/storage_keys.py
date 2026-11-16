"""Server-owned, persistent company namespaces; legacy objects remain readable."""

import re
from .errors import WebsiteError

CATEGORIES = {"IMAGE": "media", "LOGO": "logo", "FAVICON": "logo", "BANNER": "banners", "PROMOTION": "promotions", "SECTION": "sections"}


def website_storage_prefix(website):
    prefix = website.storage_prefix or f"companies/{website.company_id}"
    if not re.fullmatch(r"[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)*", prefix) or len(prefix) > 160:
        raise WebsiteError("El prefijo de almacenamiento requiere conciliación administrativa.", code="MEDIA_UNAVAILABLE", status=503)
    return prefix


def build_website_media_key(website, kind, media_id):
    if kind not in CATEGORIES:
        raise WebsiteError("Categoría de imagen inválida.")
    return f"{website_storage_prefix(website)}/website/{CATEGORIES[kind]}/{media_id}"


def owns_media_key(website, key):
    if key.startswith(f"websites/{website.pk}/media/"):
        return True
    return any(key.startswith(f"{website_storage_prefix(website)}/website/{category}/") for category in set(CATEGORIES.values()))
