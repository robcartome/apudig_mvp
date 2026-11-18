from django.db.models import Q

from apps.users.models import RolePermission, UserRole
from apps.users.permissions import user_is_company_admin, user_store_role
from apps.websites.permissions import WebsiteAccessDenied, website_capabilities


def catalog_capabilities(*, user, company_id, store_id=None):
    context, editorial = website_capabilities(user, company_id, store_id)
    policy_admin = user.is_superuser or user_is_company_admin(user, context.company_id)
    if policy_admin:
        return {"read": True, "edit": True, "publish": True, "policy": True}
    role_ids = UserRole.objects.filter(user=user, company_id=context.company_id).values("role_id")
    grants = Q(role_id__in=role_ids)
    store_role = user_store_role(user, context.company_id, context.store_id)
    if store_role:
        grants |= Q(role__name__iexact=store_role)
    explicit_read = RolePermission.objects.filter(grants, permission__code="read.website").exists()
    return {
        "read": policy_admin or editorial["edit"] or editorial["publish"] or explicit_read,
        "edit": editorial["edit"],
        "publish": editorial["edit"] and editorial["publish"],
        "policy": policy_admin,
    }


def require_catalog_permission(*, operation, **context):
    capabilities = catalog_capabilities(**context)
    if not capabilities[operation]:
        raise WebsiteAccessDenied("No tienes permiso para esta operación comercial.")
    return capabilities
