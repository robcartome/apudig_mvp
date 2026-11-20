"""Prepared requests with live confirmation; external messaging is gated."""
import hashlib
import json
import re
import secrets
from datetime import timedelta
from uuid import UUID
from urllib.parse import quote

from django.db import transaction
from django.utils import timezone
from apps.core.models import AuditLog

from apps.websites.accounts import resolve_commercial_account
from apps.websites.catalog.quotation import recalculate_commercial_cart, validate_cart_items
from apps.websites.errors import WebsiteError
from apps.websites.models import CommercialConsent, CommercialOrderRequest, Website
from apps.websites.registration import policy_for
from apps.websites.public_content import published_content


def requests_enabled(hostname):
    # Same effective persistent opt-in as the public Website and profile.
    return published_content(hostname)["commerceEnabled"] is True


def effective_status(request):
    return "EXPIRED" if request.status == "PREPARED" and request.expires_at <= timezone.now() else request.status


def request_data(request, *, allow_whatsapp=False):
    link = None
    if allow_whatsapp and request.share_confirmed and effective_status(request) == "PREPARED":
        lines = [f"Solicitud AP-{request.pk.hex}"]
        lines += [f"{item['name']}: {item['quantity']} {item['unit']} · {item['total']} {request.offer['currency']}" for item in request.offer["items"]]
        lines += [f"Total: {request.offer['total']} {request.offer['currency']}", "Pendiente de confirmación por la empresa. Sin reserva de stock."]
        link = f"https://wa.me/{request.destination_phone}?text={quote(chr(10).join(lines), safe='')}"
    return {"id": str(request.pk), "reference": "AP-" + request.pk.hex, "status": effective_status(request), "createdAt": request.created_at, "expiresAt": request.expires_at, "offer": request.offer, "note": request.note, "whatsappUrl": link}


@transaction.atomic
def prepare_request(*, user, hostname, items, offer_fingerprint, note, idempotency_key, share_confirmed):
    """Domain engine. HTTP callers must additionally pass requests_enabled.

    Keeping the gate in the application layer permits isolated domain tests
    while every real API write stays closed until the pilot is accepted.
    """
    website, account = resolve_commercial_account(user, hostname)
    if share_confirmed is not True:
        raise WebsiteError("Confirma que deseas preparar el resumen para compartirlo por WhatsApp.", code="SHARE_CONFIRMATION_REQUIRED")
    Website.objects.select_for_update().get(pk=website.pk)
    website, account = resolve_commercial_account(user, hostname)
    policy = policy_for(website)
    if policy is None:
        raise WebsiteError("El aviso de privacidad no está configurado.", code="PRIVACY_UNAVAILABLE", status=503)
    if not CommercialConsent.objects.filter(user=user, notice=policy.notice).exists():
        raise WebsiteError("Revisa y acepta el aviso vigente antes de preparar la solicitud.", code="CONSENT_REQUIRED", status=409)
    validated = validate_cart_items(items)
    try:
        key = UUID(str(idempotency_key))
    except (ValueError, TypeError, AttributeError) as exc:
        raise WebsiteError("Idempotency-Key debe ser una referencia válida.") from exc
    if not isinstance(note, str) or len(note) > 500:
        raise WebsiteError("La observación admite hasta 500 caracteres.")
    canonical = {"items": [[str(product), str(unit), quantity] for product, unit, quantity in validated], "note": note, "offerFingerprint": offer_fingerprint, "notice": str(policy.notice_id)}
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing = CommercialOrderRequest.objects.filter(website=website, account=account, idempotency_key=key).first()
    if existing and (existing.body_digest != digest or existing.customer_id != account.customer_id):
        raise WebsiteError("La referencia de reintento corresponde a otra solicitud.", code="IDEMPOTENCY_CONFLICT", status=409)
    current = recalculate_commercial_cart(user, hostname, items)
    if not isinstance(offer_fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", offer_fingerprint) or not secrets.compare_digest(current["offerFingerprint"], offer_fingerprint):
        raise WebsiteError("La oferta cambió. Revisa el resumen antes de preparar la solicitud.", code="OFFER_CHANGED", status=409)
    published = published_content(hostname)
    phone = published["content"]["contact"]["whatsapp"]
    if not re.fullmatch(r"[0-9]{8,15}", phone):
        raise WebsiteError("El contacto de la empresa no está disponible.", code="CONTACT_UNAVAILABLE", status=503)
    if existing:
        if effective_status(existing) != "PREPARED" or existing.editorial_revision != published["revision"] or existing.destination_phone != phone:
            raise WebsiteError("La solicitud anterior cambió o caducó. Revisa una nueva solicitud.", code="REQUEST_EXPIRED", status=409)
        return existing
    row = CommercialOrderRequest.objects.create(website=website, account=account, customer_id=account.customer_id, privacy_notice=policy.notice, idempotency_key=key, body_digest=digest, offer=current, note=note, destination_phone=phone, editorial_revision=published["revision"], share_confirmed=True, expires_at=timezone.now() + timedelta(minutes=15))
    AuditLog.objects.create(user=user, action="COMMERCIAL_REQUEST_PREPARED", entity="CommercialOrderRequest", entity_id=str(row.pk), meta_data={"websiteId": str(website.pk), "noticeVersion": policy.notice.version})
    return row


def owned_requests(user, hostname):
    website, account = resolve_commercial_account(user, hostname)
    return CommercialOrderRequest.objects.filter(website=website, account=account, customer_id=account.customer_id)


def current_request_data(row, user, hostname):
    """History is immutable; a link is withheld if its offer/contact is stale."""
    allowed = requests_enabled(hostname)
    if allowed and effective_status(row) == "PREPARED":
        try:
            items = [{"productId": line["productId"], "unitId": line["unitId"], "quantity": line["quantity"]} for line in row.offer["items"]]
            offer = recalculate_commercial_cart(user, hostname, items)
            content = published_content(hostname)
            allowed = secrets.compare_digest(offer["offerFingerprint"], row.offer["offerFingerprint"]) and content["content"]["contact"]["whatsapp"] == row.destination_phone and content["revision"] == row.editorial_revision
        except WebsiteError:
            allowed = False
    return {**request_data(row, allow_whatsapp=allowed), "reviewRequired": not allowed}
