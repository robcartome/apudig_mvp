from rest_framework.views import APIView

from apps.core.managers import filter_by_company


class BaseCompanyAPIView(APIView):
    """Reusable API base that resolves and applies active company scoping."""

    company_required = False

    def get_company_id(self):
        raw_request = getattr(self.request, "_request", None)

        auth_company_id = None
        if isinstance(self.request.auth, dict):
            auth_company_id = self.request.auth.get("company_id")

        active_company_id = (
            getattr(self.request, "active_company_id", None)
            or (getattr(raw_request, "active_company_id", None) if raw_request else None)
        )
        session = getattr(raw_request, "session", None) if raw_request else None
        session_company_id = session.get("active_company_id") if session is not None else None

        company_id = (
            auth_company_id
            or active_company_id
            or session_company_id
        )

        if self.company_required and not company_id:
            return None
        return company_id

    def scope_queryset(self, queryset):
        return filter_by_company(queryset, self.get_company_id())
