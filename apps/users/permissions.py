"""Evaluación central de permisos por empresa para vistas web."""

from .models import Permission, UserRole


def user_has_company_permission(user, company_id, permission_code: str) -> bool:
    """Autoriza superusuarios y permisos asignados mediante roles de empresa.

    Mientras un módulo no tenga permisos configurados se conserva el acceso
    legado. En cuanto existan permisos para ese módulo, se aplica denegación
    por defecto.
    """
    if not user or not user.is_authenticated or not company_id:
        return False
    if user.is_superuser:
        return True

    module = permission_code.split(".", 1)[1] if "." in permission_code else ""
    if module and not Permission.objects.filter(module=module).exists():
        return True

    return UserRole.objects.filter(
        user=user,
        company_id=company_id,
        role__role_permissions__permission__code=permission_code,
    ).exists()
