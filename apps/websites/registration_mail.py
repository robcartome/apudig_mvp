"""Explicit SMTP adapter and bounded outbox; secrets never enter the queue."""
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.websites.catalog.selectors import public_website
from apps.websites.errors import WebsiteError
from apps.websites.models import CommercialRegistration, WebsiteEmailOutbox


def provider_ready():
    try:
        validate_email(settings.WEBSITE_EMAIL_FROM)
        port_valid = 1 <= settings.WEBSITE_SMTP_PORT <= 65535
    except (ValidationError, TypeError):
        return False
    host = settings.WEBSITE_SMTP_HOST
    return bool(settings.WEBSITE_EMAIL_BACKEND == "smtp" and host and not any(character.isspace() for character in host) and port_valid and (settings.WEBSITE_SMTP_USE_TLS != settings.WEBSITE_SMTP_USE_SSL))


def require_provider():
    if not provider_ready():
        raise WebsiteError("El servicio de verificación no está disponible.", code="EMAIL_UNAVAILABLE", status=503)


def deliver_email(recipient, subject, body):
    require_provider()
    connection = get_connection(
        backend="django.core.mail.backends.smtp.EmailBackend",
        host=settings.WEBSITE_SMTP_HOST, port=settings.WEBSITE_SMTP_PORT,
        username=settings.WEBSITE_SMTP_USER, password=settings.WEBSITE_SMTP_PASSWORD,
        use_tls=settings.WEBSITE_SMTP_USE_TLS, use_ssl=settings.WEBSITE_SMTP_USE_SSL,
        timeout=10, fail_silently=False,
    )
    if EmailMessage(subject, body, settings.WEBSITE_EMAIL_FROM, [recipient], connection=connection).send() != 1:
        raise RuntimeError("EmailNotAccepted")


def verification_url(hostname, route, secret):
    origin = "https://" + hostname
    configured = settings.WEBSITE_EMAIL_DEV_ORIGIN
    if settings.DEBUG and hostname.endswith(".localhost") and configured:
        try:
            parsed = urlsplit(configured)
            valid = (parsed.scheme in ("http", "https") and parsed.hostname == hostname and not parsed.username and not parsed.password and parsed.path in ("", "/") and not parsed.query and not parsed.fragment and (parsed.port is None or 1 <= parsed.port <= 65535))
        except ValueError:
            valid = False
        if valid:
            origin = configured.rstrip("/")
    return f"{origin}/{route}#token={secret}"


def send_queued_emails(*, limit=20):
    require_provider()
    sent, failed = 0, 0
    for _ in range(max(0, min(limit, 100))):
        with transaction.atomic():
            now = timezone.now()
            job = WebsiteEmailOutbox.objects.select_for_update(skip_locked=True).filter(
                Q(status__in=("QUEUED", "FAILED")) | Q(status="SENDING", last_attempt_at__lt=now - timedelta(minutes=15)),
                attempts__lt=3,
            ).filter(Q(last_attempt_at__isnull=True) | Q(last_attempt_at__lt=now - timedelta(minutes=1))).order_by("created_at").first()
            if job is None:
                break
            registration = CommercialRegistration.objects.select_for_update().select_related("notice").get(pk=job.registration_id)
            job.attempts += 1
            job.last_attempt_at, job.status = now, "SENDING"
            job.save(update_fields=["attempts", "last_attempt_at", "status", "updated_at"])
            secret = secrets.token_urlsafe(32)
            registration.token_digest = hashlib.sha256(secret.encode()).hexdigest()
            registration.expires_at = min(now + timedelta(minutes=30), registration.created_at + timedelta(days=registration.notice.pending_retention_days))
            registration.save(update_fields=["token_digest", "expires_at", "updated_at"])
        try:
            if registration.consumed_at or registration.expires_at <= now:
                raise RuntimeError("RegistrationExpired")
            website = public_website(job.hostname)
            if website.pk != registration.website_id:
                raise RuntimeError("WebsiteMismatch")
            # Fragment keeps the one-use secret out of HTTP access logs/RSC.
            route = "recuperar-cuenta" if registration.purpose == "RECOVERY" else "verificar-cuenta"
            url = verification_url(job.hostname, route, secret)
            deliver_email(registration.email, "Verifica tu solicitud en APUDIG", f"Se solicitó una operación en tu cuenta. Si no la solicitaste, ignora este correo.\n\n{url}\n\nEl enlace tiene una vigencia máxima de 30 minutos y solo puede utilizarse una vez.")
        except Exception as exc:
            # SMTP errors may contain recipients or credentials. Persist only
            # an exception class, never the raw message or delivery body.
            WebsiteEmailOutbox.objects.filter(pk=job.pk).update(status="FAILED", error_code=type(exc).__name__[:80])
            failed += 1
        else:
            WebsiteEmailOutbox.objects.filter(pk=job.pk).update(status="SENT", error_code="")
            sent += 1
    return {"sent": sent, "failed": failed}
