from rest_framework.permissions import BasePermission

from apps.users.permissions import user_can_access_context, user_has_company_permission


def _request_context(request):
    auth_company_id = None
    auth_store_id = None
    if isinstance(request.auth, dict):
        auth_company_id = request.auth.get("company_id")
        auth_store_id = request.auth.get("store_id")

    raw_request = getattr(request, "_request", request)
    session = getattr(raw_request, "session", {})
    company_id = (
        auth_company_id
        or getattr(raw_request, "active_company_id", None)
        or session.get("active_company_id")
    )
    store_id = (
        auth_store_id
        or getattr(raw_request, "active_store_id", None)
        or session.get("active_store_id")
    )
    return company_id, store_id


class IsCompanyUser(BasePermission):
    """Require an authenticated user with an active company context."""

    message = "No existe contexto de empresa activa para esta solicitud."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        company_id, store_id = _request_context(request)
        return user_can_access_context(request.user, company_id, store_id)


class HasCompanyPermission(BasePermission):
    """Require a current authorized tenant and the permission declared by a view."""

    message = "No tiene acceso o permisos para la empresa activa."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        company_id, store_id = _request_context(request)
        if not user_can_access_context(request.user, company_id, store_id):
            return False

        permission_resolver = getattr(view, "get_required_company_permission", None)
        if callable(permission_resolver):
            permission_code = permission_resolver()
        else:
            permission_code = getattr(view, "required_company_permission", None)
        if not permission_code:
            return True
        return user_has_company_permission(
            request.user,
            company_id,
            permission_code,
            store_id,
        )
