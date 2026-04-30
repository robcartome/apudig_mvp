"""
core/mixins.py — Mixins reutilizables para vistas basadas en clases.

Jerarquía recomendada:
    class MyView(ActiveCompanyRequiredMixin, CompanyScopedMixin, View): ...
    class MySecureView(RoleRequiredMixin, View):
        required_roles = ["ADMIN"]
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseForbidden
from django.shortcuts import redirect


class ActiveCompanyRequiredMixin(LoginRequiredMixin):
    """
    Garantiza: usuario autenticado + empresa activa en sesión.
    Redirige a 'select_company' si falta la empresa.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not getattr(request, "active_company_id", None):
            return redirect("select_company")
        return super().dispatch(request, *args, **kwargs)


class CompanyScopedMixin:
    """
    Expone company_id y store_id activos como propiedades de la vista
    e inyecta sus valores en el contexto de template.
    Usar siempre junto a ActiveCompanyRequiredMixin.
    """

    @property
    def active_company_id(self) -> str | None:
        return self.request.active_company_id  # type: ignore[attr-defined]

    @property
    def active_store_id(self) -> str | None:
        return self.request.active_store_id  # type: ignore[attr-defined]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)  # type: ignore[misc]
        ctx["active_company_id"] = self.active_company_id
        ctx["active_store_id"] = self.active_store_id
        return ctx


class RoleRequiredMixin(LoginRequiredMixin):
    """
    Garantiza: autenticado + empresa activa + rol requerido en sucursal.
    Incluye las propiedades de CompanyScopedMixin para conveniencia.

    Uso:
        class MyView(RoleRequiredMixin, ListView):
            required_roles = ["ADMIN", "SELLER"]
    """

    required_roles: list[str] = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not getattr(request, "active_company_id", None):
            return redirect("select_company")
        if self.required_roles and not self._user_has_role(request):
            return HttpResponseForbidden(
                "No tienes permiso para acceder a esta sección."
            )
        return super().dispatch(request, *args, **kwargs)

    # --- propiedades de scoping ---

    @property
    def active_company_id(self) -> str | None:
        return self.request.active_company_id  # type: ignore[attr-defined]

    @property
    def active_store_id(self) -> str | None:
        return self.request.active_store_id  # type: ignore[attr-defined]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)  # type: ignore[misc]
        ctx["active_company_id"] = self.active_company_id
        ctx["active_store_id"] = self.active_store_id
        return ctx

    # --- verificación de rol ---

    def _user_has_role(self, request) -> bool:
        from apps.users.models import UserStore

        store_id = getattr(request, "active_store_id", None)
        if not store_id:
            return False
        return UserStore.objects.filter(
            user=request.user,
            store_id=store_id,
            role__in=self.required_roles,
            is_active=True,
        ).exists()
