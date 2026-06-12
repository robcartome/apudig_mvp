from rest_framework.permissions import BasePermission


class IsCompanyUser(BasePermission):
    """Require an authenticated user with an active company context."""

    message = "No existe contexto de empresa activa para esta solicitud."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        auth_company_id = None
        if isinstance(request.auth, dict):
            auth_company_id = request.auth.get("company_id")

        active_company_id = getattr(request, "active_company_id", None) or request.session.get("active_company_id")
        return bool(auth_company_id or active_company_id)
