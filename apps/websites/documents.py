"""Versioned frontend document contract. No demo products, HTML or inline files."""

import json
import re
from copy import deepcopy
from datetime import datetime
from urllib.parse import urlsplit

from .errors import WebsiteError, invalid_document


DOCUMENT_SCHEMA_VERSION = 3
DOCUMENT_MAX_BYTES = 256 * 1024
SECTION_TYPES = ("benefits", "categories", "announcements", "specials", "featured", "promotions", "about")
ART_TYPES = ("drill", "grinder", "cement", "paint", "pipe", "cable", "helmet", "brick")
BADGE_POSITIONS = ("top-left", "top-right", "bottom-left", "bottom-right")
SOCIAL_HOSTS = {
    "facebook": ("facebook.com", "fb.com"), "instagram": ("instagram.com",),
    "tiktok": ("tiktok.com",), "youtube": ("youtube.com", "youtu.be"), "x": ("x.com", "twitter.com"),
}
_EMAIL = re.compile(r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]*[A-Z0-9])?(?:\.[A-Z0-9](?:[A-Z0-9-]*[A-Z0-9])?)+$", re.I | re.ASCII)
_MARKUP = re.compile(r"<\s*(?:/?[a-zA-Z]|!)")


def is_plain_text(value, maximum, required=False):
    return isinstance(value, str) and len(value) <= maximum and (not required or bool(value.strip())) and not _MARKUP.search(value) and "\x00" not in value


def safe_link(value):
    return isinstance(value, str) and len(value) <= 300 and value.startswith("/") and not value.startswith("//") and not re.search(r"[\\\s\x00-\x1f<>]", value)


def safe_image(value):
    if not isinstance(value, str) or len(value) > 1000:
        return False
    if not value:
        return True
    if re.search(r"[\\\s\x00-\x1f]", value):
        return False
    if value.startswith("/"):
        return bool(safe_link(value))
    try:
        url = urlsplit(value)
        url.port  # Validate malformed/out-of-range ports even for HTTPS URLs.
        return url.scheme == "https" and bool(url.hostname) and not url.username and not url.password
    except ValueError:
        return False


def default_document(name):
    name = name[:100]
    return {
        "schemaVersion": 3,
        "identity": {"name": name, "shortName": name[:40], "location": "Por configurar", "primaryColor": "#FF8000", "logoUrl": "", "announcement": ""},
        "contact": {"phone": "", "secondaryPhone": "", "email": "", "whatsapp": "", "address": "", "hours": "", "socials": {}},
        "seo": {"title": name[:70], "description": "Información comercial de la empresa."},
        "heroSlider": {"autoplay": True, "intervalMs": 6000},
        "banners": [], "announcements": {"ctaLabel": "Contacto", "href": "/contact", "items": []},
        "specials": {"productIds": []}, "promotions": [],
        "sections": [{"type": kind, "enabled": False, "title": kind.capitalize()} for kind in SECTION_TYPES],
    }


def upgrade_website_document(document):
    """Explicit import adapter; HTTP saves still require schema v3."""
    result = deepcopy(document)
    if not isinstance(result, dict):
        raise invalid_document({"document": "Formato no compatible."})
    if type(result.get("schemaVersion")) is not int:
        raise invalid_document({"schemaVersion": "Versión no compatible."})
    if result.get("schemaVersion") == 1:
        for collection in ("banners", "promotions"):
            items = result.get(collection, [])
            if not isinstance(items, list):
                raise invalid_document({collection: "Colección no válida."})
            for item in items:
                if isinstance(item, dict) and isinstance(item.get("href"), str):
                    item["href"] = re.sub(r"^/catalog(?=$|[/?#])", "/shop", item["href"])
        result["schemaVersion"] = 2
    if result.get("schemaVersion") == 2:
        sections = result.get("sections", [])
        if not isinstance(sections, list) or any(not isinstance(item, dict) for item in sections):
            raise invalid_document({"sections": "Secciones no válidas."})
        added = [{"type": kind, "enabled": False, "title": kind.capitalize()} for kind in ("announcements", "specials") if not any(item.get("type") == kind for item in sections)]
        position = next((i + 1 for i, item in enumerate(sections) if item.get("type") == "categories"), 0)
        sections[position:position] = added
        result.setdefault("announcements", {"ctaLabel": "Contacto", "href": "/contact", "items": []})
        result.setdefault("specials", {"productIds": []})
        result["schemaVersion"] = 3
    return normalize_document(result)


def normalize_document(document):
    """Validate the complete v3 shape, retaining optional notice fields and order."""
    try:
        encoded = json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError):
        raise invalid_document({"document": "JSON no válido."})
    if len(encoded) > DOCUMENT_MAX_BYTES:
        raise WebsiteError("El documento supera 256 KiB.", code="PAYLOAD_TOO_LARGE", status=413)
    errors = {}

    def obj(value, path, allowed, required=None):
        if not isinstance(value, dict):
            errors[path] = "Se requiere un objeto."
            return {}
        for key in set(value) - set(allowed):
            errors[f"{path}.{key}" if path else key] = "Campo no permitido."
        for key in required or ():
            if key not in value:
                errors[f"{path}.{key}" if path else key] = "Campo obligatorio."
        return value

    def text(value, path, maximum, required=False):
        if not is_plain_text(value, maximum, required):
            errors[path] = f"Usa texto plano {'obligatorio, ' if required else ''}de hasta {maximum} caracteres."

    def boolean(value, path):
        if type(value) is not bool:
            errors[path] = "Se requiere booleano."

    def link(value, path):
        if not safe_link(value):
            errors[path] = "Usa un enlace interno válido."

    def image(value, path):
        if not safe_image(value):
            errors[path] = "Usa una imagen gestionada; no se aceptan data URLs."

    def ids(value, path, limit):
        if not isinstance(value, list) or len(value) > limit or any(not isinstance(item, str) or not item for item in value) or len(set(map(str, value))) != len(value):
            errors[path] = f"Hasta {limit} identificadores únicos."

    def collection(value, path, limit):
        if not isinstance(value, list) or len(value) > limit:
            errors[path] = f"Se permiten hasta {limit} elementos."
            return []
        return value

    root_keys = {"schemaVersion", "identity", "contact", "seo", "heroSlider", "banners", "announcements", "specials", "promotions", "sections"}
    root = obj(document, "", root_keys, root_keys - {"heroSlider"})
    if type(root.get("schemaVersion")) is not int or root.get("schemaVersion") != 3:
        errors["schemaVersion"] = "Se requiere documento editorial v3."
    identity = obj(root.get("identity"), "identity", ("name", "shortName", "location", "primaryColor", "logoUrl", "announcement"))
    for key, maximum in (("name", 100), ("shortName", 40), ("location", 100), ("announcement", 180)):
        text(identity.get(key), f"identity.{key}", maximum, key != "announcement")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(identity.get("primaryColor", ""))):
        errors["identity.primaryColor"] = "Usa #RRGGBB."
    image(identity.get("logoUrl"), "identity.logoUrl")
    contact = obj(root.get("contact"), "contact", ("phone", "secondaryPhone", "email", "whatsapp", "address", "hours", "socials"))
    for key, maximum in (("phone", 40), ("whatsapp", 15), ("address", 300), ("hours", 180), ("secondaryPhone", 40), ("email", 180)):
        text(contact.get(key, "") if key in ("secondaryPhone", "email") else contact.get(key), f"contact.{key}", maximum)
    if contact.get("email") and not _EMAIL.fullmatch(str(contact["email"])):
        errors["contact.email"] = "Correo no válido."
    if contact.get("whatsapp") and not re.fullmatch(r"[0-9]{8,15}", str(contact["whatsapp"])):
        errors["contact.whatsapp"] = "Incluye país y 8–15 dígitos."
    socials = obj(contact.get("socials", {}), "contact.socials", SOCIAL_HOSTS)
    for network, value in socials.items():
        text(value, f"contact.socials.{network}", 300)
        if not isinstance(value, str) or not value or network not in SOCIAL_HOSTS:
            continue
        try:
            url = urlsplit(value)
            valid = url.scheme == "https" and not url.username and not url.password and url.port in (None, 443) and not re.search(r"\s", value) and any(url.hostname == host or (url.hostname or "").endswith("." + host) for host in SOCIAL_HOSTS[network])
        except (ValueError, TypeError):
            valid = False
        if not valid:
            errors[f"contact.socials.{network}"] = "Perfil HTTPS del proveedor requerido."
    seo = obj(root.get("seo"), "seo", ("title", "description"))
    text(seo.get("title"), "seo.title", 70, True)
    text(seo.get("description"), "seo.description", 180, True)
    slider = obj(root.get("heroSlider", {"autoplay": True, "intervalMs": 6000}), "heroSlider", ("autoplay", "intervalMs"))
    boolean(slider.get("autoplay"), "banners.autoplay")
    interval = slider.get("intervalMs")
    if type(interval) is not int or not 3000 <= interval <= 15000:
        errors["banners.intervalMs"] = "Intervalo entero entre 3000 y 15000."
    announcements = obj(root.get("announcements"), "announcements", ("ctaLabel", "href", "items"))
    text(announcements.get("ctaLabel"), "announcements.ctaLabel", 40, True)
    link(announcements.get("href"), "announcements.href")
    specials = obj(root.get("specials"), "specials", ("productIds",))
    ids(specials.get("productIds"), "specials.productIds", 4)

    specs = (("banners", root.get("banners"), 12), ("promotions", root.get("promotions"), 12), ("announcements.items", announcements.get("items"), 8))
    for path, values, maximum in specs:
        seen = set()
        for index, raw in enumerate(collection(values, path, maximum)):
            prefix = f"{path}.{index}"
            common = {"id", "enabled", "title", "description", "ctaLabel", "href"}
            extra = {"eyebrow", "imageUrl", "mobileImageUrl", "imageAlt", "art"} if path == "banners" else {"eyebrow", "startsAt", "endsAt", "productIds"} if path == "promotions" else {"badge", "badgePosition", "imageUrl", "imageAlt", "art"}
            item = obj(raw, prefix, common | extra)
            item_id = item.get("id")
            if not isinstance(item_id, str) or not re.fullmatch(r"[\w-]{1,80}", item_id, re.ASCII) or item_id in seen:
                errors[f"{prefix}.id"] = "Identificador inválido o duplicado."
            else:
                seen.add(item_id)
            boolean(item.get("enabled"), f"{prefix}.enabled")
            text(item.get("title"), f"{prefix}.title", 100, True)
            text(item.get("description", "") if path == "announcements.items" else item.get("description"), f"{prefix}.description", 180 if path == "announcements.items" else 300)
            if path != "announcements.items" or "ctaLabel" in item:
                text(item.get("ctaLabel"), f"{prefix}.ctaLabel", 40, True)
            link(item.get("href"), f"{prefix}.href")
            if path == "promotions":
                text(item.get("eyebrow"), f"{prefix}.eyebrow", 60)
                ids(item.get("productIds"), f"{prefix}.productIds", 50)
                dates = []
                for key in ("startsAt", "endsAt"):
                    value = item.get(key)
                    try:
                        if value == "":
                            dates.append(None)
                        elif isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", value):
                            dates.append(datetime.fromisoformat(value.replace("Z", "+00:00")))
                        else:
                            raise ValueError
                    except ValueError:
                        errors[f"{prefix}.{key}"] = "Fecha UTC no válida."
                        dates.append(None)
                if all(dates) and dates[1] <= dates[0]:
                    errors[f"{prefix}.endsAt"] = "El fin debe ser posterior al inicio."
                continue
            if item.get("art") not in ART_TYPES:
                errors[f"{prefix}.art"] = "Ilustración no válida."
            image(item.get("imageUrl"), f"{prefix}.imageUrl")
            text(item.get("imageAlt"), f"{prefix}.imageAlt", 180)
            if path == "banners":
                text(item.get("eyebrow"), f"{prefix}.eyebrow", 60)
                image(item.get("mobileImageUrl"), f"{prefix}.mobileImageUrl")
                if item.get("mobileImageUrl") and not item.get("imageUrl"):
                    errors[f"{prefix}.imageUrl"] = "Agrega primero la imagen desktop."
            else:
                text(item.get("badge"), f"{prefix}.badge", 40)
                if item.get("badgePosition") not in BADGE_POSITIONS:
                    errors[f"{prefix}.badgePosition"] = "Posición inválida."
            if (item.get("imageUrl") or item.get("mobileImageUrl")) and not str(item.get("imageAlt", "")).strip():
                errors[f"{prefix}.imageAlt"] = "Describe la imagen."
    sections = collection(root.get("sections"), "sections", 7)
    kinds = []
    for index, raw in enumerate(sections):
        section = obj(raw, f"sections.{index}", ("type", "enabled", "title"))
        kinds.append(section.get("type"))
        boolean(section.get("enabled"), f"sections.{index}.enabled")
        text(section.get("title"), f"sections.{index}.title", 100, True)
    if len(kinds) != 7 or any(not isinstance(kind, str) for kind in kinds) or set(map(str, kinds)) != set(SECTION_TYPES):
        errors["sections"] = "Incluye cada sección exactamente una vez."
    if errors:
        raise invalid_document(errors)
    result = deepcopy(document)
    result.setdefault("heroSlider", {"autoplay": True, "intervalMs": 6000})
    for key, default in (("secondaryPhone", ""), ("email", ""), ("socials", {})):
        result["contact"].setdefault(key, default)
    return result
