import hashlib
import json
import logging
import secrets
import time
from urllib.request import Request, urlopen

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .blocks import validate_block_config
from .models import (
    WebsiteMenu, WebsiteMenuItem, WebsitePage, WebsitePageRevision, WebsiteSection,
)


logger = logging.getLogger(__name__)

HOME_SINGLETON_SECTIONS = {
    "hero.v1", "categories.v1", "featured_products.v1", "brands.v1",
    "benefits.v1", "contact.v1", "whatsapp_cta.v1",
}
HOME_ONLY_SECTIONS = HOME_SINGLETON_SECTIONS - {"hero.v1", "benefits.v1", "contact.v1"}


def validate_page_sections(page, sections):
    seen = set()
    for section in sections:
        section_type = section.section_type if isinstance(section, WebsiteSection) else section["section_type"]
        if section_type in HOME_ONLY_SECTIONS and page.page_type != WebsitePage.PageType.HOME:
            raise ValidationError({"sections": "La sección solo se permite en la página de inicio."})
        if page.page_type == WebsitePage.PageType.HOME and section_type in HOME_SINGLETON_SECTIONS:
            if section_type in seen:
                raise ValidationError({"sections": "La página de inicio contiene una sección duplicada."})
            seen.add(section_type)


class PageVersionConflict(Exception):
    pass


class MenuVersionConflict(Exception):
    pass


def issue_domain_verification_token(domain) -> str:
    """Issue a one-time DNS token while persisting only its SHA-256 hash."""
    token = secrets.token_urlsafe(32)
    domain.verification_token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    domain.save(update_fields=("verification_token_hash", "updated_at"))
    return token


def build_page_snapshot(page):
    validate_page_sections(page, list(page.sections.all()))
    sections = []
    for section in page.sections.filter(enabled=True).order_by("position"):
        sections.append({
            "id": str(section.id),
            "section_type": section.section_type,
            "schema_version": section.schema_version,
            "position": section.position,
            "enabled": True,
            "config": validate_block_config(
                section.section_type, section.schema_version, section.config
            ),
        })
    return {
        "page": {
            "id": str(page.id), "slug": page.slug, "title": page.title,
            "page_type": page.page_type, "seo_title": page.seo_title,
            "seo_description": page.seo_description,
            "og_image_url": page.og_image_url, "noindex": page.noindex,
        },
        "sections": sections,
    }


@transaction.atomic
def replace_page_sections(*, page, sections, expected_version, actor):
    locked = WebsitePage.objects.select_for_update().get(pk=page.pk)
    if locked.draft_version != expected_version:
        raise PageVersionConflict
    validate_page_sections(locked, sections)
    validated = []
    for position, section in enumerate(sections):
        if section.get("position", position) != position:
            raise ValueError("Las posiciones deben ser consecutivas y comenzar en cero.")
        config = validate_block_config(
            section["section_type"], section.get("schema_version", 1), section.get("config", {})
        )
        validated.append(WebsiteSection(
            page=locked, section_type=section["section_type"],
            schema_version=section.get("schema_version", 1), position=position,
            enabled=section.get("enabled", True), config=config,
        ))
    locked.sections.all().delete()
    WebsiteSection.objects.bulk_create(validated)
    locked.draft_version += 1
    locked.updated_by = actor
    locked.save(update_fields=("draft_version", "updated_by", "updated_at"))
    return locked


@transaction.atomic
def publish_page(*, page, expected_version, actor):
    locked = WebsitePage.objects.select_for_update().prefetch_related("sections").get(pk=page.pk)
    if locked.draft_version != expected_version:
        raise PageVersionConflict
    snapshot = build_page_snapshot(locked)
    version = locked.published_version + 1
    revision = WebsitePageRevision.objects.create(
        page=locked, version=version, snapshot=snapshot, created_by=actor
    )
    locked.status = WebsitePage.Status.PUBLISHED
    locked.published_version = version
    locked.published_at = timezone.now()
    locked.updated_by = actor
    locked.save(update_fields=("status", "published_version", "published_at", "updated_by", "updated_at"))
    transaction.on_commit(lambda: send_storefront_revalidation(locked))
    return locked, revision


@transaction.atomic
def restore_page_revision(*, page, version, expected_version, actor):
    locked = WebsitePage.objects.select_for_update().get(pk=page.pk)
    if locked.draft_version != expected_version:
        raise PageVersionConflict
    revision = WebsitePageRevision.objects.get(page=locked, version=version)
    snapshot = revision.snapshot
    sections = snapshot.get("sections", [])
    validate_page_sections(locked, sections)
    restored = []
    for position, section in enumerate(sections):
        config = validate_block_config(section["section_type"], section.get("schema_version", 1), section["config"])
        restored.append(WebsiteSection(
            page=locked, section_type=section["section_type"],
            schema_version=section.get("schema_version", 1), position=position,
            enabled=section.get("enabled", True), config=config,
        ))
    locked.sections.all().delete()
    WebsiteSection.objects.bulk_create(restored)
    for field in ("title", "seo_title", "seo_description", "og_image_url", "noindex"):
        if field in snapshot.get("page", {}):
            setattr(locked, field, snapshot["page"][field])
    locked.draft_version += 1
    locked.updated_by = actor
    locked.save(update_fields=("title", "seo_title", "seo_description", "og_image_url", "noindex", "draft_version", "updated_by", "updated_at"))
    return locked


def create_preview_token(page):
    return signing.dumps(
        {"page_id": str(page.id), "website_id": str(page.website_id), "draft_version": page.draft_version},
        salt="website-page-preview",
        compress=True,
    )


def read_preview_token(token):
    return signing.loads(
        token, salt="website-page-preview",
        max_age=getattr(settings, "WEBSITE_PREVIEW_TOKEN_TTL", 900),
    )


def revalidation_payload(page):
    tags = [f"site:{page.website_id}", f"page:{page.website_id}:{page.slug}"]
    for hostname in page.website.domains.filter(status="ACTIVE").values_list("hostname", flat=True):
        tags.extend((f"host:{hostname}", f"page-host:{hostname}:{page.slug}"))
    return {"tags": tags}


def send_storefront_revalidation(page):
    url = getattr(settings, "STOREFRONT_REVALIDATE_URL", "")
    secret = getattr(settings, "STOREFRONT_REVALIDATE_SECRET", "")
    if not url or not secret:
        return
    body = json.dumps(revalidation_payload(page)).encode("utf-8")
    request = Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {secret}",
        "X-APUDIG-Timestamp": str(int(time.time())),
    })
    try:
        with urlopen(request, timeout=2):  # noqa: S310 - URL is deployment configuration.
            pass
    except Exception:
        logger.exception("Storefront revalidation failed for page %s", page.pk)


def _menu_item_href(item):
    if item.target_type == WebsiteMenuItem.TargetType.PAGE:
        return "/" if item.page.slug == "home" else f"/{item.page.slug}"
    return item.url


def build_menu_snapshot(menu):
    roots = list(
        menu.items.filter(parent__isnull=True, enabled=True)
        .select_related("page").order_by("position")
    )
    snapshot = []
    for root in roots:
        children = list(
            root.children.filter(enabled=True).select_related("page").order_by("position")
        )
        serialize = lambda item: {
            "id": str(item.id), "label": item.label, "href": _menu_item_href(item),
            "open_in_new_tab": item.open_in_new_tab,
        }
        root_data = serialize(root)
        root_data["children"] = [serialize(child) for child in children]
        snapshot.append(root_data)
    return snapshot


@transaction.atomic
def replace_menu_items(*, menu, items, expected_version):
    locked = WebsiteMenu.objects.select_for_update().get(pk=menu.pk)
    if locked.draft_version != expected_version:
        raise MenuVersionConflict
    locked.items.all().delete()
    created_by_index = {}
    for index, data in enumerate(items):
        parent_index = data.get("parent_index")
        parent = None
        if parent_index is not None:
            parent = created_by_index.get(parent_index)
            if parent is None or parent.parent_id:
                raise ValidationError("El elemento padre debe ser un elemento raíz anterior.")
        page = None
        if data["target_type"] == WebsiteMenuItem.TargetType.PAGE:
            try:
                page = WebsitePage.objects.get(pk=data.get("page_id"), website=locked.website)
            except WebsitePage.DoesNotExist as exc:
                raise ValidationError("La página del menú no pertenece al sitio.") from exc
        item = WebsiteMenuItem(
            menu=locked, parent=parent, position=data["position"], label=data["label"],
            target_type=data["target_type"], page=page, url=data.get("url", ""),
            open_in_new_tab=data.get("open_in_new_tab", False), enabled=data.get("enabled", True),
        )
        item.save()
        created_by_index[index] = item
    locked.draft_version += 1
    locked.save(update_fields=("draft_version", "updated_at"))
    return locked


@transaction.atomic
def publish_menu(*, menu, expected_version):
    locked = WebsiteMenu.objects.select_for_update().get(pk=menu.pk)
    if locked.draft_version != expected_version:
        raise MenuVersionConflict
    locked.published_items = build_menu_snapshot(locked)
    locked.published_version += 1
    locked.status = WebsiteMenu.Status.PUBLISHED
    locked.published_at = timezone.now()
    locked.save(update_fields=("published_items", "published_version", "status", "published_at", "updated_at"))
    transaction.on_commit(lambda: send_website_revalidation(locked.website))
    return locked


def send_website_revalidation(website):
    url = getattr(settings, "STOREFRONT_REVALIDATE_URL", "")
    secret = getattr(settings, "STOREFRONT_REVALIDATE_SECRET", "")
    if not url or not secret:
        return
    tags = [f"site:{website.pk}", f"catalog:{website.pk}"]
    for hostname in website.domains.filter(status="ACTIVE").values_list("hostname", flat=True):
        tags.append(f"host:{hostname}")
    body = json.dumps({"tags": tags}).encode("utf-8")
    request = Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {secret}",
        "X-APUDIG-Timestamp": str(int(time.time())),
    })
    try:
        with urlopen(request, timeout=2):  # noqa: S310
            pass
    except Exception:
        logger.exception("Storefront revalidation failed for website %s", website.pk)
