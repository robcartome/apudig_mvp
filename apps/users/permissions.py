"""Evaluación central de permisos por empresa para vistas web."""

from .models import Permission, Role, UserRole, UserStore


COMPANY_ADMIN_ROLE = "ADMIN"


def user_is_company_admin(user, company_id) -> bool:
    """Return whether the user administers the selected company."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if not company_id:
        return False
    return UserRole.objects.filter(
        user=user,
        company_id=company_id,
        role__name__iexact=COMPANY_ADMIN_ROLE,
    ).exists()


def user_store_role(user, company_id, store_id) -> str | None:
    """Return the active role assigned to a user in a specific store."""
    if not user or not user.is_authenticated or not company_id or not store_id:
        return None
    if user.is_superuser or user_is_company_admin(user, company_id):
        return COMPANY_ADMIN_ROLE
    return (
        UserStore.objects.filter(
            user=user,
            store_id=store_id,
            store__company_id=company_id,
            store__active=True,
            is_active=True,
        )
        .values_list("role", flat=True)
        .first()
    )


def user_can_access_context(user, company_id, store_id=None) -> bool:
    """Validate tenant and branch membership independently from session data."""
    if not user or not user.is_authenticated or not company_id:
        return False
    from apps.companies.models import Company, Store

    if not Company.objects.filter(pk=company_id, is_active=True).exists():
        return False
    if store_id and not Store.objects.filter(
        pk=store_id,
        company_id=company_id,
        active=True,
    ).exists():
        return False
    if user.is_superuser or user_is_company_admin(user, company_id):
        return True
    if store_id:
        return user_store_role(user, company_id, store_id) is not None
    return user.company_accesses.filter(
        company_id=company_id,
        store__isnull=True,
    ).exists()


def user_has_company_permission(
    user,
    company_id,
    permission_code: str,
    store_id=None,
) -> bool:
    """Autoriza superusuarios y permisos asignados mediante roles de empresa.

    Mientras un módulo no tenga permisos configurados se conserva el acceso
    legado. En cuanto existan permisos para ese módulo, se aplica denegación
    por defecto.
    """
    if not user or not user.is_authenticated or not company_id:
        return False
    if user.is_superuser or user_is_company_admin(user, company_id):
        return True

    store_role = user_store_role(user, company_id, store_id)
    if store_role == COMPANY_ADMIN_ROLE:
        return True

    module = permission_code.split(".", 1)[1] if "." in permission_code else ""
    if module and not Permission.objects.filter(module=module).exists():
        return True

    company_role_grants = UserRole.objects.filter(
        user=user,
        company_id=company_id,
        role__role_permissions__permission__code=permission_code,
    ).exists()
    if company_role_grants:
        return True

    return bool(store_role) and Role.objects.filter(
        name__iexact=store_role,
        role_permissions__permission__code=permission_code,
    ).exists()
