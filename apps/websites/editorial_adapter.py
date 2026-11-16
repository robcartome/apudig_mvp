"""Map one mutable draft to existing settings/page/section entities."""

from copy import deepcopy

from .documents import default_document, normalize_document
from .errors import WebsiteError
from .models import WebsitePage, WebsiteSection, WebsiteSettings


HERO_BLOCK = "hero_slider.v1"
SECTION_BLOCKS = {
    "benefits": "editorial_benefits.v1", "categories": "editorial_categories.v1",
    "announcements": "announcements.v1", "specials": "specials.v1",
    "featured": "editorial_featured.v1", "promotions": "promotions.v1", "about": "editorial_about.v1",
}
EDITORIAL_BLOCKS = {HERO_BLOCK, *SECTION_BLOCKS.values()}
IDENTITY_FIELDS = {
    "name": "business_name", "shortName": "short_name", "location": "location",
    "primaryColor": "primary_color", "logoUrl": "logo_url", "announcement": "announcement",
}
CONTACT_FIELDS = {
    "phone": "phone", "secondaryPhone": "secondary_phone", "email": "email",
    "whatsapp": "whatsapp", "address": "address", "hours": "hours_text", "socials": "social_links",
}


def home_page(website):
    return WebsitePage.objects.filter(website=website, page_type="HOME").first()


def read_draft(website):
    result = default_document(website.name)
    settings = WebsiteSettings.objects.filter(website=website).first()
    page = home_page(website)
    sections = list(page.sections.order_by("position")) if page else []
    if sections and (len(sections) != 8 or {section.section_type for section in sections} != EDITORIAL_BLOCKS):
        raise WebsiteError("El contenido histórico requiere una conversión explícita antes de editarlo.", code="LEGACY_CONTENT_REQUIRES_MIGRATION", status=409)
    if settings:
        for target, source in IDENTITY_FIELDS.items():
            value = getattr(settings, source)
            # New optional fields can be empty on historical, unconfigured sites.
            if value or target not in ("name", "shortName", "location"):
                result["identity"][target] = deepcopy(value)
        for target, source in CONTACT_FIELDS.items():
            result["contact"][target] = deepcopy(getattr(settings, source))
        if settings.default_seo_title:
            result["seo"]["title"] = settings.default_seo_title
        if settings.default_seo_description:
            result["seo"]["description"] = settings.default_seo_description
    if page:
        if page.seo_title:
            result["seo"]["title"] = page.seo_title
        if page.seo_description:
            result["seo"]["description"] = page.seo_description
    if sections:
        hero = next(section for section in sections if section.section_type == HERO_BLOCK)
        result.update(deepcopy(hero.config))
        reverse = {block: kind for kind, block in SECTION_BLOCKS.items()}
        result["sections"] = []
        for section in sections:
            if section.section_type == HERO_BLOCK:
                continue
            kind = reverse[section.section_type]
            result["sections"].append({"type": kind, "title": section.config["title"], "enabled": section.enabled})
            if kind in ("announcements", "specials", "promotions"):
                result[kind] = deepcopy(section.config["content"])
    return normalize_document(result)


def write_draft(website, document, actor, media_references):
    # Caller holds the Website row lock and has validated the complete document.
    settings, _ = WebsiteSettings.objects.get_or_create(website=website)
    for source, target in IDENTITY_FIELDS.items():
        setattr(settings, target, deepcopy(document["identity"][source]))
    for source, target in CONTACT_FIELDS.items():
        setattr(settings, target, deepcopy(document["contact"][source]))
    settings.logo_media_id = media_references.get("identity.logoUrl")
    settings.save()
    page = home_page(website)
    if page is None:
        page = WebsitePage(website=website, page_type="HOME", slug="home", created_by=actor)
    page.title = document["identity"]["name"]
    page.seo_title = document["seo"]["title"]
    page.seo_description = document["seo"]["description"]
    page.updated_by = actor
    page.draft_version = website.editorial_revision
    page.save()
    page.sections.all().delete()
    rows = [WebsiteSection(page=page, section_type=HERO_BLOCK, schema_version=1, position=0, enabled=True, config={"banners": deepcopy(document["banners"]), "heroSlider": deepcopy(document["heroSlider"])})]
    for position, section in enumerate(document["sections"], 1):
        kind = section["type"]
        config = {"title": section["title"]}
        if kind in ("announcements", "specials", "promotions"):
            config["content"] = deepcopy(document[kind])
        rows.append(WebsiteSection(page=page, section_type=SECTION_BLOCKS[kind], schema_version=1, position=position, enabled=section["enabled"], config=config))
    WebsiteSection.objects.bulk_create(rows)
    return page


def validate_editorial_block(section_type, schema_version, config):
    if schema_version != 1 or not isinstance(config, dict):
        raise WebsiteError("Bloque no válido.")
    document = default_document("Validación")
    if section_type == HERO_BLOCK:
        if set(config) != {"banners", "heroSlider"}:
            raise WebsiteError("Configuración de hero no válida.")
        document.update(deepcopy(config))
    else:
        kind = next(kind for kind, block in SECTION_BLOCKS.items() if block == section_type)
        allowed = {"title", "content"} if kind in ("announcements", "specials", "promotions") else {"title"}
        if set(config) != allowed:
            raise WebsiteError("Configuración de sección no válida.")
        next(section for section in document["sections"] if section["type"] == kind)["title"] = config["title"]
        if "content" in config:
            document[kind] = config["content"]
    normalize_document(document)
    return deepcopy(config)
