"""
core/mixins.py — Mixins reutilizables para vistas basadas en clases.

Jerarquía recomendada para vistas de negocio:

    class MyView(ActiveCompanyRequiredMixin, CompanyScopedMixin, View):
        ...
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect


class ActiveCompanyRequiredMixin(LoginRequiredMixin):
    """
    Garantiza que el usuario está autenticado Y tiene empresa activa en sesión.
    Redirige a 'select_company' si falta la empresa.
    """

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        # super() puede devolver una redirección a login; respetarla.
        if response.status_code != 200:
            return response
        if not request.active_company_id:
            return redirect("select_company")
        return response


class CompanyScopedMixin:
    """
    Inyecta company_id y store_id activos como propiedades de la vista.
    Usar siempre junto a ActiveCompanyRequiredMixin.

    Ejemplo:
        qs = Product.objects.for_company(self.active_company_id).active()
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
