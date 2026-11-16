"""Website authorization uses current ERP membership and explicit grants."""

import uuid
from dataclasses import dataclass

from django.core.exceptions import PermissionDenied
from django.db.models import Q

from apps.companies.models import UserCompanyAccess
from apps.users.models import RolePermission, UserRole
from apps.users.permissions import (
    user_can_access_context,
    user_is_company_admin,
    user_store_role,
)


WEBSITE_PERMISSIONS = {
    "view": "read.website",
    "edit": "manage.website",
    "publish": "publish.website",
    "mediaUpload": "manage.website.media",
    "domains": "manage.website.domains",
}


class WebsiteAccessDenied(PermissionDenied):
    def __init__(self, message="No tiene acceso a la empresa activa.", code="FORBIDDEN"):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class WebsiteContext:
    company_id: uuid.UUID
    store_id: uuid.UUID | None


def _context_uuid(value, *, required=False):
    if value in (None, ""):
        if required:
            raise WebsiteAccessDenied("Debe seleccionar una empresa activa.", "COMPANY_REQUIRED")
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise WebsiteAccessDenied() from exc


def authorize_website_context(user, company_id, store_id=None):
    """Reject missing context before any Website query; do not trust JWT grants."""
    company_id = _context_uuid(company_id, required=True)
    store_id = _context_uuid(store_id)
    if not user or not user.is_authenticated or not user.is_active:
        raise WebsiteAccessDenied()
    # Website requires a current access row even if an old company-admin role
    # remains. Superusers retain their explicit ERP administrative exception.
    if not user.is_superuser:
        accesses = UserCompanyAccess.objects.filter(user=user, company_id=company_id)
        if store_id:
            accesses = accesses.filter(Q(store__isnull=True) | Q(store_id=store_id))
        else:
            accesses = accesses.filter(store__isnull=True)
        if not accesses.exists():
            raise WebsiteAccessDenied()
    if not user_can_access_context(user, company_id, store_id):
        raise WebsiteAccessDenied()
    return WebsiteContext(company_id=company_id, store_id=store_id)


def website_capabilities(user, company_id, store_id=None):
    """Return current authorization, without the ERP's unconfigured-module bypass."""
    context = authorize_website_context(user, company_id, store_id)
    store_role = user_store_role(user, context.company_id, context.store_id)
    administrator = user.is_superuser or user_is_company_admin(user, context.company_id) or store_role == "ADMIN"
    if administrator:
        grants = set(WEBSITE_PERMISSIONS.values())
    else:
        roles = UserRole.objects.filter(user=user, company_id=context.company_id).values("role_id")
        grant_filter = Q(role_id__in=roles)
        if store_role:
            grant_filter |= Q(role__name__iexact=store_role)
        grants = set(
            RolePermission.objects.filter(
                grant_filter,
                permission__code__in=WEBSITE_PERMISSIONS.values(),
            ).values_list("permission__code", flat=True)
        )
    capabilities = {key: code in grants for key, code in WEBSITE_PERMISSIONS.items()}
    capabilities["view"] = any(capabilities.values())
    capabilities["realPublication"] = True
    return context, capabilities


def require_website_permission(user, company_id, permission, store_id=None):
    if permission not in WEBSITE_PERMISSIONS:
        raise ValueError("Capacidad Website desconocida.")
    context, capabilities = website_capabilities(user, company_id, store_id)
    if not capabilities[permission]:
        raise WebsiteAccessDenied("No tiene permisos sobre el website de esta empresa.")
    return context
