"""
core/managers.py — Managers y QuerySets reutilizables.

Regla: todas las entidades que pertenezcan a una empresa (company_id)
o sucursal (store_id) deben usar CompanyScopedManager para garantizar
que el filtrado multiempresa sea siempre consistente.
"""
from django.db import models


class CompanyScopedQuerySet(models.QuerySet):
    """QuerySet con helpers para filtrado multiempresa."""

    def for_company(self, company_id: str) -> "CompanyScopedQuerySet":
        return self.filter(company_id=company_id)

    def for_store(self, store_id: str) -> "CompanyScopedQuerySet":
        return self.filter(store_id=store_id)

    def active(self) -> "CompanyScopedQuerySet":
        return self.filter(active=True)


class CompanyScopedManager(models.Manager):
    """
    Manager que expone los métodos de CompanyScopedQuerySet directamente.

    Uso en un modelo:

        class MyModel(models.Model):
            company = models.ForeignKey(Company, ...)
            objects = CompanyScopedManager()

        # En una vista:
        MyModel.objects.for_company(request.active_company_id).active()
    """

    def get_queryset(self) -> CompanyScopedQuerySet:
        return CompanyScopedQuerySet(self.model, using=self._db)

    def for_company(self, company_id: str) -> CompanyScopedQuerySet:
        return self.get_queryset().for_company(company_id)

    def for_store(self, store_id: str) -> CompanyScopedQuerySet:
        return self.get_queryset().for_store(store_id)

    def active(self) -> CompanyScopedQuerySet:
        return self.get_queryset().active()
