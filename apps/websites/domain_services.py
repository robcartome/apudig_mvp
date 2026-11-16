"""Domain administration. Lock Website before domains; never publish implicitly."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.companies.models import Company
from apps.core.models import AuditLog
from .models import Website, WebsiteDomain
from .permissions import require_website_permission
from .services import locked_website


def audit(user, website, action, **metadata):
    AuditLog.objects.create(user=user, action=action, entity="Website", entity_id=str(website.pk), meta_data=metadata)


@transaction.atomic
def create_company_website(*, user, company_id, store_id=None):
    require_website_permission(user, company_id, "edit", store_id)
    company = Company.objects.select_for_update().get(pk=company_id, is_active=True)
    website, created = Website.objects.get_or_create(company=company, defaults={"name": company.name, "created_by": user, "updated_by": user})
    if created:
        audit(user, website, "WEBSITE_CREATE")
    return website


@transaction.atomic
def register_domain(*, user, company_id, website_id, hostname, kind, store_id=None):
    website = locked_website(user=user, company_id=company_id, website_id=website_id, store_id=store_id, permission="domains")
    domain = WebsiteDomain.objects.create(website=website, hostname=hostname, kind=kind)
    audit(user, website, "WEBSITE_DOMAIN_REGISTER", domainId=str(domain.pk), hostname=domain.hostname)
    return domain


@transaction.atomic
def change_domain(*, user, company_id, website_id, domain_id, operation, evidence="", store_id=None):
    website = locked_website(user=user, company_id=company_id, website_id=website_id, store_id=store_id, permission="domains")
    domain = WebsiteDomain.objects.select_for_update().get(pk=domain_id, website=website)
    if operation == "verify":
        # Operational attestation, not an automated DNS check or a client status patch.
        if not user.is_superuser:
            raise PermissionDenied("Solo personal APUDIG puede registrar la verificación de control del dominio.")
        evidence = evidence.strip()
        if not 20 <= len(evidence) <= 1000:
            raise ValidationError("Describe la comprobación realizada (20 a 1000 caracteres, sin secretos).")
        if domain.status == WebsiteDomain.Status.ACTIVE:
            raise ValidationError("Desactiva el dominio antes de registrar una nueva verificación.")
        domain.status = WebsiteDomain.Status.VERIFIED
        domain.verified_at = timezone.now()
    elif operation == "activate":
        if domain.status != WebsiteDomain.Status.VERIFIED or not domain.verified_at:
            raise ValidationError("Primero se debe verificar el control del dominio.")
        domain.status = WebsiteDomain.Status.ACTIVE
    elif operation == "primary":
        if domain.status != WebsiteDomain.Status.ACTIVE or not domain.verified_at:
            raise ValidationError("El dominio principal debe estar activo y verificado.")
        WebsiteDomain.objects.filter(website=website, is_primary=True).exclude(pk=domain.pk).update(is_primary=False)
        domain.is_primary = True
    elif operation == "disable":
        domain.is_primary = False
        domain.status = WebsiteDomain.Status.DISABLED
        domain.verified_at = None
    else:
        raise ValidationError("Operación de dominio desconocida.")
    domain.save()
    audit(user, website, "WEBSITE_DOMAIN_" + operation.upper(), domainId=str(domain.pk), hostname=domain.hostname, **({"evidence": evidence, "verification": "manual_operational_attestation"} if operation == "verify" else {}))
    return domain
