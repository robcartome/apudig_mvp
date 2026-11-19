"""Commercial account core; no public registration or contact delivery.

The future verification provider must deliver the returned secret to the
recipient. It must never return it in an HTTP response or write it to logs.
"""
import hashlib
import secrets
from datetime import timedelta

from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.models import AuditLog
from apps.partners.models import SalesCustomerProfile
from apps.websites.catalog.permissions import require_catalog_permission
from apps.websites.catalog.selectors import public_website
from apps.websites.errors import WebsiteError
from apps.websites.models import CommercialAccount, CommercialEmailChallenge


def account_denied():
    return WebsiteError("La cuenta comercial no está disponible.", code="COMMERCIAL_ACCESS_DENIED", status=403)


def active_account(user, company_id, *, require_verified=True):
    if not user or not user.is_authenticated:
        raise account_denied()
    current_user = get_user_model().objects.filter(pk=user.pk, is_active=True).only("email", "updated_at").first()
    if current_user is None:
        raise account_denied()
    account = CommercialAccount.objects.filter(
        user=current_user, company_id=company_id, company__is_active=True, status=CommercialAccount.Status.ACTIVE,
        customer__active=True, customer__company_id=company_id,
    ).select_related("customer").first()
    if account is None:
        raise account_denied()
    # Conservative until a dedicated contact-change workflow exists: any user
    # profile/password update requires a fresh proof, even if email is restored.
    if require_verified and (account.verified_at is None or account.verified_at < current_user.updated_at or account.verified_email != current_user.email.strip().lower()):
        raise account_denied()
    return account


def resolve_commercial_account(user, hostname):
    website = public_website(hostname)
    return website, active_account(user, website.company_id)


def customer_price_list(account):
    """Only an approved account may use its canonical ERP customer list."""
    # Never trust approval/contact state cached by an earlier request.
    account = active_account(account.user, account.company_id)
    if account.wholesale_approved_at is None:
        return None
    return _configured_customer_price_list(account)


def _configured_customer_price_list(account):
    profile = SalesCustomerProfile.objects.filter(
        customer_id=account.customer_id, customer__company_id=account.company_id,
        customer__active=True, active=True, price_list__active=True,
        price_list__company_id=account.company_id,
    ).select_related("price_list").first()
    # No fallback when an approved account has a missing or revoked list.
    if profile is None:
        raise WebsiteError("No hay una lista comercial autorizada.", code="CUSTOMER_PRICE_UNAVAILABLE", status=409)
    return profile.price_list


@transaction.atomic
def issue_email_challenge(user, website):
    account = active_account(user, website.company_id, require_verified=False)
    account = CommercialAccount.objects.select_for_update().get(pk=account.pk)
    active_account(user, website.company_id, require_verified=False)
    now = timezone.now()
    # One active delivery per account; prevents a future UI from invalidating
    # links uncontrollably. Provider/IP/global quotas are still required.
    if account.email_challenges.filter(created_at__gt=now - timedelta(minutes=1)).exists():
        raise WebsiteError("Espera antes de solicitar otro enlace.", code="RATE_LIMITED", status=429)
    account.email_challenges.filter(consumed_at__isnull=True).update(consumed_at=now)
    secret = secrets.token_urlsafe(32)
    CommercialEmailChallenge.objects.create(
        account=account, email=account.user.email.strip().lower(),
        token_digest=hashlib.sha256(secret.encode()).hexdigest(),
        expires_at=now + timedelta(minutes=30),
    )
    return secret


@transaction.atomic
def verify_email_challenge(user, website, secret):
    account = active_account(user, website.company_id, require_verified=False)
    account = CommercialAccount.objects.select_for_update().get(pk=account.pk)
    active_account(user, website.company_id, require_verified=False)
    if not isinstance(secret, str) or not 20 <= len(secret) <= 200:
        raise account_denied()
    now = timezone.now()
    challenge = CommercialEmailChallenge.objects.filter(
        account=account, token_digest=hashlib.sha256(secret.encode()).hexdigest(),
        consumed_at__isnull=True, expires_at__gt=now, email=account.user.email.strip().lower(),
        created_at__gte=account.user.updated_at,
    ).first()
    if challenge is None:
        raise account_denied()
    challenge.consumed_at = now
    challenge.save(update_fields=["consumed_at", "updated_at"])
    account.verified_email, account.verified_at = challenge.email, now
    account.save(update_fields=["verified_email", "verified_at", "updated_at"])
    return account


@transaction.atomic
def set_wholesale_approval(*, user, company_id, account_id, approved, store_id=None):
    require_catalog_permission(user=user, company_id=company_id, store_id=store_id, operation="policy")
    account = CommercialAccount.objects.select_for_update().select_related("user", "customer").filter(
        pk=account_id, company_id=company_id, customer__company_id=company_id,
    ).first()
    if account is None:
        raise account_denied()
    require_catalog_permission(user=user, company_id=company_id, store_id=store_id, operation="policy")
    if type(approved) is not bool:
        raise WebsiteError("Indica si autorizas el acceso mayorista.")
    if approved:
        from apps.websites.models import Website
        website = Website.objects.get(company_id=company_id)
        active_account(account.user, website.company_id)
        # Validate the configured list before granting access, without changing
        # any fiscal or commercial fields on Customer/SalesCustomerProfile.
        _configured_customer_price_list(account)
    account.wholesale_approved_at = timezone.now() if approved else None
    account.wholesale_approved_by = user if approved else None
    account.save(update_fields=["wholesale_approved_at", "wholesale_approved_by", "updated_at"])
    AuditLog.objects.create(user=user, action="COMMERCIAL_WHOLESALE_APPROVAL", entity="CommercialAccount", entity_id=str(account.pk), meta_data={"approved": approved, "companyId": str(company_id)})
    return account
