"""Explicit commercial purpose on the existing User/JWT mechanism."""
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from apps.api.v1.auth.tokens import build_token
from apps.websites.accounts import active_account
from apps.websites.catalog.selectors import public_website
from apps.websites.errors import WebsiteError
from apps.websites.models import CommercialSession, normalize_hostname


def invalid_session():
    return WebsiteError("La sesión comercial no está disponible. Inicia sesión de nuevo.", code="COMMERCIAL_SESSION_INVALID", status=401)


def require_session_schema():
    # A pending additive migration must not turn the existing Website into a
    # 500 or trigger an automatic migration against its habitual database.
    if CommercialSession._meta.db_table not in connection.introspection.table_names():
        raise WebsiteError("El servicio de cuentas no está disponible temporalmente.", code="COMMERCIAL_UNAVAILABLE", status=503)


def session_claims(session):
    return {"sub": str(session.account.user_id), "purpose": "commercial", "session_id": str(session.pk), "hostname": session.hostname, "website_id": str(session.website_id)}


def session_tokens(session, *, include_refresh=True):
    remaining = session.expires_at - timezone.now()
    claims = session_claims(session)
    access = build_token({**claims, "type": "access"}, min(settings.JWT_ACCESS_TTL, remaining))
    result = {"context": "commercial", "websiteId": str(session.website_id), "access": access, "access_token": access}
    if include_refresh:
        refresh = build_token({**claims, "type": "refresh"}, remaining)
        result.update(refresh=refresh, refresh_token=refresh)
    return result


def start_session(user, hostname):
    try:
        hostname = normalize_hostname(hostname)
    except ValidationError as exc:
        raise invalid_session() from exc
    website = public_website(hostname)
    account = active_account(user, website.company_id)
    require_session_schema()
    session = CommercialSession.objects.create(
        account=account, website=website, customer_id=account.customer_id,
        hostname=hostname, verified_at=account.verified_at,
        auth_hash=user.get_session_auth_hash(), expires_at=timezone.now() + settings.JWT_REFRESH_TTL,
    )
    return session_tokens(session)


def resolve_session(payload, hostname):
    if not isinstance(payload, dict) or payload.get("purpose") != "commercial" or payload.get("hostname") != hostname:
        raise invalid_session()
    try:
        session_id, user_id, website_id = (UUID(str(payload.get(key))) for key in ("session_id", "sub", "website_id"))
    except (ValueError, TypeError, AttributeError) as exc:
        raise invalid_session() from exc
    require_session_schema()
    session = CommercialSession.objects.select_related("account__user", "website").filter(
        pk=session_id, account__user_id=user_id, website_id=website_id,
        hostname=hostname, revoked_at__isnull=True, expires_at__gt=timezone.now(),
    ).first()
    if session is None:
        raise invalid_session()
    user = get_user_model().objects.get(pk=user_id)
    website = public_website(hostname)
    account = active_account(user, website.company_id)
    if (website.pk != session.website_id or account.pk != session.account_id or
        account.customer_id != session.customer_id or account.verified_at != session.verified_at or
        not constant_time_compare(session.auth_hash, user.get_session_auth_hash())):
        raise invalid_session()
    return session, user, website, account


def refresh_session(payload, hostname):
    session, _, _, _ = resolve_session(payload, hostname)
    return session_tokens(session, include_refresh=False)


def revoke_session(payload):
    if not isinstance(payload, dict) or payload.get("purpose") != "commercial":
        return
    try:
        session_id, user_id = UUID(str(payload.get("session_id"))), UUID(str(payload.get("sub")))
    except (ValueError, TypeError, AttributeError):
        return
    CommercialSession.objects.filter(pk=session_id, account__user_id=user_id, revoked_at__isnull=True).update(revoked_at=timezone.now())
