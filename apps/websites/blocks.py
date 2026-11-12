import json
import re
from copy import deepcopy
from urllib.parse import urlparse

from django.core.exceptions import ValidationError


BLOCK_DEFINITIONS = {
    "hero.v1": {"title": (str, 120, True), "subtitle": (str, 300, False), "cta_label": (str, 40, False), "cta_url": (str, 1000, False), "image_url": (str, 1000, False), "overlay": (int, None, False)},
    "image_text.v1": {"title": (str, 120, True), "body": (str, 2000, True), "image_url": (str, 1000, False), "alignment": (str, 10, False)},
    "benefits.v1": {"title": (str, 120, False), "items": (list, None, True)},
    "contact.v1": {"title": (str, 120, False), "show_whatsapp": (bool, None, False), "show_phone": (bool, None, False), "show_address": (bool, None, False)},
    "categories.v1": {"title": (str, 120, False), "limit": (int, None, False)},
    "featured_products.v1": {"title": (str, 120, False), "limit": (int, None, False)},
    "brands.v1": {"title": (str, 120, False), "limit": (int, None, False)},
    "whatsapp_cta.v1": {"title": (str, 120, True), "body": (str, 300, False), "button_label": (str, 40, False)},
}
_UNSAFE_MARKUP = re.compile(r"<\s*/?\s*(script|iframe|object|embed|style)|javascript:", re.I)


def _validate_text(value, field, max_length):
    if _UNSAFE_MARKUP.search(value):
        raise ValidationError({"config": f"'{field}' contiene contenido no permitido."})
    if max_length and len(value) > max_length:
        raise ValidationError({"config": f"'{field}' supera {max_length} caracteres."})


def _validate_url(value, field):
    if not value:
        return
    parsed = urlparse(value)
    if value.startswith("/") and not value.startswith("//"):
        return
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValidationError({"config": f"'{field}' debe ser una ruta interna o URL HTTPS."})


def validate_block_config(section_type, schema_version, config):
    if schema_version != 1 or section_type not in BLOCK_DEFINITIONS:
        raise ValidationError({"section_type": "Tipo o versión de bloque no soportado."})
    if not isinstance(config, dict):
        raise ValidationError({"config": "La configuración debe ser un objeto JSON."})
    if len(json.dumps(config, ensure_ascii=False)) > 20_000:
        raise ValidationError({"config": "La configuración del bloque es demasiado grande."})
    definition = BLOCK_DEFINITIONS[section_type]
    unknown = set(config) - set(definition)
    if unknown:
        raise ValidationError({"config": f"Campos no permitidos: {', '.join(sorted(unknown))}."})
    normalized = deepcopy(config)
    for field, (expected_type, max_length, required) in definition.items():
        if required and field not in config:
            raise ValidationError({"config": f"Falta el campo requerido '{field}'."})
        if field not in config:
            continue
        value = config[field]
        if type(value) is not expected_type:
            raise ValidationError({"config": f"'{field}' tiene un tipo inválido."})
        if expected_type is str:
            _validate_text(value, field, max_length)
    if section_type == "hero.v1":
        if not 0 <= normalized.get("overlay", 35) <= 100:
            raise ValidationError({"config": "'overlay' debe estar entre 0 y 100."})
        _validate_url(normalized.get("cta_url", ""), "cta_url")
        _validate_url(normalized.get("image_url", ""), "image_url")
    elif section_type == "image_text.v1":
        if normalized.get("alignment", "left") not in {"left", "right"}:
            raise ValidationError({"config": "'alignment' debe ser left o right."})
        _validate_url(normalized.get("image_url", ""), "image_url")
    elif section_type == "benefits.v1":
        items = normalized["items"]
        if not 1 <= len(items) <= 6:
            raise ValidationError({"config": "Incluya entre 1 y 6 beneficios."})
        for item in items:
            if not isinstance(item, dict) or set(item) - {"title", "text", "icon"}:
                raise ValidationError({"config": "Cada beneficio contiene campos inválidos."})
            if not isinstance(item.get("title"), str) or not item["title"]:
                raise ValidationError({"config": "Cada beneficio requiere un título."})
            if not isinstance(item.get("text", ""), str):
                raise ValidationError({"config": "El texto del beneficio es inválido."})
            _validate_text(item["title"], "items.title", 80)
            _validate_text(item.get("text", ""), "items.text", 240)
            if item.get("icon", "shield") not in {"shield", "truck", "tools", "support"}:
                raise ValidationError({"config": "El icono del beneficio no está permitido."})
    elif section_type in {"categories.v1", "featured_products.v1", "brands.v1"}:
        if not 1 <= normalized.get("limit", 8) <= 24:
            raise ValidationError({"config": "El límite debe estar entre 1 y 24."})
    return normalized
