"""Registration proofs and canonical Customer resolution; no employee grants."""
import hashlib
import re
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.utils import timezone

from apps.companies.models import UserCompanyAccess
from apps.core.models import AuditLog
from apps.partners.models import Customer
from apps.partners.services import create_customer
from apps.users.models import UserRole, UserStore
from apps.websites.catalog.selectors import public_website
from apps.websites.catalog.services import authorized_website
from apps.websites.errors import WebsiteError
from apps.websites.models import CommercialAccount, CommercialConsent, CommercialRegistration, CommercialSession, WebsiteEmailOutbox, WebsitePrivacyNotice, WebsiteRegistrationPolicy
from apps.websites.registration_mail import provider_ready, require_provider
from apps.websites.registration_limits import consume_budget, limits_ready


def invalid_proof():
    return WebsiteError("El enlace no es válido o ha caducado.", code="INVALID_PROOF", status=400)


def policy_for(website):
    if WebsiteRegistrationPolicy._meta.db_table not in connection.introspection.table_names():
        raise WebsiteError("La configuración de registro aún no está disponible.", code="REGISTRATION_UNAVAILABLE", status=503)
    return WebsiteRegistrationPolicy.objects.select_related("notice").filter(website=website, notice__website=website).first()


def registration_enabled(policy):
    return bool(settings.WEBSITE_REGISTRATION_ENABLED and policy and provider_ready() and limits_ready())


def public_registration_policy(hostname):
    website = public_website(hostname)
    # Do not query new tables when the public feature is closed.
    if not settings.WEBSITE_REGISTRATION_ENABLED:
        return {"websiteId": str(website.pk), "registrationEnabled": False, "notice": None}
    policy = policy_for(website)
    notice = policy.notice if policy else None
    return {"websiteId": str(website.pk), "registrationEnabled": registration_enabled(policy), "notice": {"version": notice.version, "text": notice.text, "pendingRetentionDays": notice.pending_retention_days} if notice else None}


def require_registration(hostname):
    website = public_website(hostname)
    if not settings.WEBSITE_REGISTRATION_ENABLED:
        raise WebsiteError("El registro público aún no está disponible.", code="REGISTRATION_DISABLED", status=503)
    require_provider()
    policy = policy_for(website)
    if policy is None:
        raise WebsiteError("La política de registro no está configurada.", code="REGISTRATION_UNAVAILABLE", status=503)
    return website, policy


@transaction.atomic
def start_registration(hostname, *, email, name="", notice_version, consent, purpose="REGISTER", origin="internal"):
    website, policy = require_registration(hostname)
    type(website).objects.select_for_update().get(pk=website.pk)
    policy = policy_for(website)
    if consent is not True or notice_version != policy.notice.version:
        raise WebsiteError("Revisa y acepta el aviso vigente.", code="CONSENT_REQUIRED", fields={"noticeVersion": "Aviso vigente obligatorio."})
    email = email.strip().lower()
    now = timezone.now()
    # Same response and workflow for known/unknown identities; lookup of User
    # happens only after a valid proof, never in the anonymous request path.
    recent = CommercialRegistration.objects.filter(website=website, email=email, created_at__gt=now - timedelta(minutes=1)).exists()
    if recent:
        return
    consume_budget(hostname, email, origin)
    registration = CommercialRegistration.objects.create(website=website, email=email, name=name, purpose=purpose, notice=policy.notice, consented_at=now, expires_at=now + timedelta(minutes=30))
    WebsiteEmailOutbox.objects.create(registration=registration, hostname=hostname)


def validated_password(password, email):
    if not isinstance(password, str) or not password:
        raise WebsiteError("Introduce una contraseña válida.", fields={"password": "Contraseña obligatoria."})
    candidate = get_user_model()(email=email)
    try:
        password_validation.validate_password(password, candidate)
    except ValidationError as exc:
        raise WebsiteError("Revisa la contraseña.", fields={"password": " ".join(exc.messages)}) from exc


def pending_proof(hostname, secret, purpose):
    website, policy = require_registration(hostname)
    type(website).objects.select_for_update().get(pk=website.pk)
    policy = policy_for(website)
    if not isinstance(secret, str) or not re.fullmatch(r"[A-Za-z0-9_-]{40,100}", secret):
        raise invalid_proof()
    registration = CommercialRegistration.objects.select_for_update().select_related("notice").filter(
        website=website, token_digest=hashlib.sha256(secret.encode()).hexdigest(),
        purpose=purpose, consumed_at__isnull=True, expires_at__gt=timezone.now(),
    ).first()
    if registration is None:
        raise invalid_proof()
    if registration.notice_id != policy.notice_id:
        raise WebsiteError("El aviso cambió. Solicita un nuevo enlace y revisa el aviso actual.", code="NOTICE_CHANGED", status=409)
    return website, policy, registration


def apply_verified_account(registration, account):
    if account.status != "ACTIVE" or not account.customer.active or account.customer.company_id != registration.website.company_id:
        raise WebsiteError("La cuenta requiere asistencia de la empresa.", code="ACCOUNT_REVIEW_REQUIRED", status=403)
    account.verified_email = registration.email
    account.verified_at = timezone.now()
    account.save(update_fields=["verified_email", "verified_at", "updated_at"])
    registration.account, registration.status = account, "COMPLETE"


@transaction.atomic
def complete_registration(hostname, *, secret, password="", identity=None):
    website, policy, registration = pending_proof(hostname, secret, "REGISTER")
    # Serialize competing signups within this tenant. Canonical lower-case
    # email also uses the existing unique User.email constraint across tenants.
    type(website).objects.select_for_update().get(pk=website.pk)
    users = list(get_user_model().objects.filter(email__iexact=registration.email)[:2])
    if len(users) > 1:
        raise WebsiteError("La identidad requiere revisión.", code="IDENTITY_REVIEW_REQUIRED", status=409)
    if users:
        user = users[0]
        if identity is None or identity.pk != user.pk or not user.is_active:
            raise WebsiteError("Inicia sesión con tu identidad APUDIG para completar el vínculo.", code="IDENTITY_LOGIN_REQUIRED", status=409)
        # Never set an existing identity's password/name from a signup form.
    else:
        validated_password(password, registration.email)
        try:
            with transaction.atomic():
                user = get_user_model().objects.create_user(email=registration.email, password=password, name=registration.name)
        except IntegrityError as exc:
            raise WebsiteError("La identidad ya existe. Inicia sesión para continuar.", code="IDENTITY_LOGIN_REQUIRED", status=409) from exc
    registration.user, registration.verified_at = user, timezone.now()
    CommercialConsent.objects.get_or_create(user=user, notice=registration.notice, defaults={"accepted_at": registration.consented_at})
    account = CommercialAccount.objects.select_related("customer").filter(user=user, company=website.company).first()
    if account:
        apply_verified_account(registration, account)
    else:
        # Similarity is only a review signal, never evidence of ownership.
        matches = Customer.objects.filter(company=website.company).filter(Q(email__iexact=registration.email) | Q(legal_name__iexact=registration.name)).exists()
        if policy.linking_mode == "NEW_OR_REVIEW" and not matches:
            customer = create_customer("0", "", registration.name or user.display_name, company_id=website.company_id, email=registration.email)
            account = CommercialAccount.objects.create(company=website.company, user=user, customer=customer)
            apply_verified_account(registration, account)
        else:
            registration.status = "REVIEW"
    registration.consumed_at = timezone.now()
    registration.save(update_fields=["user", "verified_at", "account", "status", "consumed_at", "updated_at"])
    return {"status": registration.status, "contactVerified": True}


@transaction.atomic
def recover_password(hostname, *, secret, password):
    website, _, registration = pending_proof(hostname, secret, "RECOVERY")
    users = list(get_user_model().objects.select_for_update().filter(email__iexact=registration.email, is_active=True)[:2])
    if len(users) != 1:
        raise invalid_proof()
    user = users[0]
    # A commercial recovery route must not silently replace the recovery policy
    # for employees, staff or mixed identities. Those need the central process.
    if user.is_staff or user.is_superuser or UserCompanyAccess.objects.filter(user=user).exists() or UserRole.objects.filter(user=user).exists() or UserStore.objects.filter(user=user).exists():
        raise WebsiteError("Solicita la recuperación de tu identidad APUDIG al administrador.", code="CENTRAL_RECOVERY_REQUIRED", status=403)
    account = CommercialAccount.objects.select_related("customer").filter(user=user, company=website.company, status="ACTIVE", customer__active=True, customer__company=website.company).first()
    if account is None:
        raise invalid_proof()
    validated_password(password, user.email)
    user.set_password(password)
    user.save(update_fields=["password", "updated_at"])
    CommercialSession.objects.filter(account__user=user, revoked_at__isnull=True).update(revoked_at=timezone.now())
    registration.user, registration.verified_at = user, timezone.now()
    apply_verified_account(registration, account)
    registration.consumed_at = timezone.now()
    registration.save(update_fields=["user", "verified_at", "account", "status", "consumed_at", "updated_at"])


@transaction.atomic
def configure_notice(*, website_id, version, text, pending_retention_days, linking_mode, expected, **context):
    website, _ = authorized_website(website_id=website_id, operation="policy", lock=True, **context)
    if expected is None:
        raise WebsiteError("Recarga la configuración antes de guardarla.", code="PRECONDITION_REQUIRED", status=428)
    if expected != policy_etag(policy_for(website)):
        raise WebsiteError("La configuración cambió. Recarga antes de continuar.", code="POLICY_CONFLICT", status=412)
    if not version.strip() or not text.strip() or not 1 <= pending_retention_days <= 36500 or linking_mode not in ("REVIEW_ALL", "NEW_OR_REVIEW"):
        raise WebsiteError("Completa el aviso y sus reglas antes de guardarlo.")
    if WebsitePrivacyNotice.objects.filter(website=website, version=version).exists():
        raise WebsiteError("Esta versión ya existe; utiliza una versión nueva.", code="NOTICE_EXISTS", status=409)
    notice = WebsitePrivacyNotice.objects.create(website=website, version=version, text=text, pending_retention_days=pending_retention_days)
    WebsiteRegistrationPolicy.objects.update_or_create(website=website, defaults={"notice": notice, "linking_mode": linking_mode})
    AuditLog.objects.create(user=context["user"], action="WEBSITE_PRIVACY_NOTICE", entity="Website", entity_id=str(website.pk), meta_data={"version": version, "digest": hashlib.sha256(text.encode()).hexdigest(), "linkingMode": linking_mode})
    return notice


def policy_etag(policy):
    value = f"{policy.pk}:{policy.notice_id}:{policy.updated_at.isoformat()}" if policy else "none"
    return '"registration-' + hashlib.sha256(value.encode()).hexdigest() + '"'


@transaction.atomic
def review_registration(*, website_id, registration_id, customer_id, **context):
    website, _ = authorized_website(website_id=website_id, operation="policy", lock=True, **context)
    registration = CommercialRegistration.objects.select_for_update(of=("self",)).select_related("user", "website").filter(pk=registration_id, website=website, status="REVIEW", verified_at__isnull=False).first()
    customer = Customer.objects.filter(pk=customer_id, company=website.company, active=True).first()
    if registration is None or customer is None:
        raise WebsiteError("No hay un vínculo autorizado para revisar.", status=404)
    if not registration.user.is_active or registration.user.updated_at > registration.verified_at or registration.user.email.strip().lower() != registration.email:
        raise WebsiteError("El contacto requiere una nueva verificación.", code="CONTACT_CHANGED", status=409)
    account = CommercialAccount.objects.filter(user=registration.user, company=website.company).first()
    if account and account.customer_id != customer.pk:
        raise WebsiteError("La cuenta ya tiene otro cliente autorizado.", code="ACCOUNT_EXISTS", status=409)
    if account is None:
        account = CommercialAccount.objects.create(user=registration.user, company=website.company, customer=customer)
    apply_verified_account(registration, account)
    registration.reviewed_by, registration.reviewed_at = context["user"], timezone.now()
    registration.save(update_fields=["account", "status", "reviewed_by", "reviewed_at", "updated_at"])
    AuditLog.objects.create(user=context["user"], action="COMMERCIAL_CUSTOMER_LINK", entity="CommercialAccount", entity_id=str(account.pk), meta_data={"registrationId": str(registration.pk), "customerId": str(customer.pk)})
