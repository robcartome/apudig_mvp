"""Recalculate a cart against live, authorized ERP offers.

This is a read-only domain service, not an order or a WhatsApp sender. Calling
it does not authorize a customer, enable commerce, or reserve inventory.
"""
import hashlib
import json
import re
import secrets
from decimal import Decimal
from uuid import UUID

from apps.inventory.pricing import money
from apps.websites.errors import WebsiteError
from .selectors import catalog_offers, public_website
from .projection import sale_unit


# Preserve the existing cart capacity. A lower operational order limit, if
# approved later, must be reported to the user without truncating their cart.
MAX_CART_LINES = 200
MAX_QUANTITY = 999


def validate_cart_items(items):
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_CART_LINES:
        raise WebsiteError("Incluye entre 1 y 200 líneas.", fields={"items": "Cantidad de líneas inválida."})
    validated, seen = [], set()
    for index, item in enumerate(items):
        path = f"items.{index}"
        if not isinstance(item, dict) or set(item) != {"productId", "unitId", "quantity"}:
            raise WebsiteError("Envía únicamente producto, unidad y cantidad.", fields={path: "Campos inválidos."})
        try:
            product_id, unit_id = UUID(str(item["productId"])), UUID(str(item["unitId"]))
        except (ValueError, TypeError, AttributeError) as exc:
            raise WebsiteError("Identificador inválido.", fields={path: "Usa UUID de producto y unidad."}) from exc
        quantity = item["quantity"]
        if type(quantity) is not int or not 1 <= quantity <= MAX_QUANTITY:
            raise WebsiteError("Cantidad inválida.", fields={f"{path}.quantity": "Usa un entero entre 1 y 999."})
        identity = (product_id, unit_id)
        if identity in seen:
            raise WebsiteError("No repitas producto y unidad.", fields={path: "Línea duplicada."})
        seen.add(identity)
        validated.append((product_id, unit_id, quantity))
    return validated


def recalculate_cart(hostname, items):
    """Return a bounded offer without customer PII, stock or internal pricing.

    Fail the entire cart if any line is invalid; never silently drop a product
    or calculate a misleading partial total. A subsequent order preparation
    must authorize the commercial account and recalculate again.
    """
    website = public_website(hostname)
    return _recalculate_cart(website, items)


def recalculate_commercial_cart(user, hostname, items):
    from apps.websites.accounts import resolve_commercial_account, customer_price_list
    website, account = resolve_commercial_account(user, hostname)
    return _recalculate_cart(website, items, customer_price_list=customer_price_list(account))


def _recalculate_cart(website, items, *, customer_price_list=None):
    validated = validate_cart_items(items)
    offers = {row.product_id: row for row in catalog_offers(website, detail=True, customer_price_list=customer_price_list).filter(
        product_id__in={row[0] for row in validated},
    )}
    lines, demand, fields = [], {}, {}
    for index, (product_id, unit_id, quantity) in enumerate(validated):
        publication = offers.get(product_id)
        path = f"items.{index}"
        if publication is None:
            fields[path] = "Producto no disponible en este catálogo."
            continue
        product = publication.product
        units = {product.unit_id: (product.unit.name, Decimal("1"))}
        for conversion in product.catalog_sale_units:
            if conversion.unit_id != product.unit_id:
                units[conversion.unit_id] = (conversion.unit.name, conversion.conversion_factor)
        if unit_id not in units:
            fields[f"{path}.unitId"] = "Unidad no disponible para este producto."
            continue
        label, factor = units[unit_id]
        offer = sale_unit(publication, unit_id, label, factor)
        if offer["price"] is None:
            fields[path] = "No hay precio autorizado para esta unidad."
            continue
        demand[product_id] = demand.get(product_id, Decimal("0")) + factor * quantity
        lines.append({
            "productId": str(product_id), "unitId": str(unit_id),
            "name": publication.offer_name, "unit": label, "quantity": quantity,
            "unitPrice": offer["price"],
            "total": format(money(Decimal(offer["price"]) * quantity), ".2f"),
            "availability": offer["availability"],
        })
    for index, (product_id, _, _) in enumerate(validated):
        publication = offers.get(product_id)
        if publication and publication.offer_availability != "unknown" and demand.get(product_id, 0) > publication.offer_stock:
            fields[f"items.{index}"] = "La cantidad solicitada supera la disponibilidad autorizada."
    if fields:
        raise WebsiteError("Revisa los productos del carrito.", code="CART_UNAVAILABLE", fields=fields, status=409)
    result = {
        "websiteId": str(website.pk), "currency": website.currency,
        "priceIncludesTax": True, "items": lines,
        "total": format(sum((Decimal(line["total"]) for line in lines), Decimal("0")), ".2f"),
    }
    # Independent from the CMS/configuration ETags: prices and availability are
    # recalculated on every call. A fingerprint is not an order authorization.
    result["offerFingerprint"] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return result


def confirm_cart_offer(hostname, items, expected_fingerprint):
    """Require review of a new calculation after any observable offer change."""
    current = recalculate_cart(hostname, items)
    if not isinstance(expected_fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_fingerprint) or not secrets.compare_digest(current["offerFingerprint"], expected_fingerprint):
        raise WebsiteError(
            "La oferta cambió. Revisa el resumen actualizado antes de continuar.",
            code="OFFER_CHANGED", status=409,
            fields={"offerFingerprint": "Solicita un nuevo cálculo y confírmalo."},
        )
    return current
