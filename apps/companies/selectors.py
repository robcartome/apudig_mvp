"""
companies/selectors.py — Consultas de lectura reutilizables.

Reglas:
- Solo SELECT, nunca modifican estado.
- Devuelven QuerySets o valores simples.
- Las vistas y los templates los consumen; no duplican lógica de filtrado.
"""
from .models import Company, Store


def get_active_companies():
    return Company.objects.filter(is_active=True).order_by("name")


def get_stores_for_company(company_id: str):
    return Store.objects.filter(company_id=company_id, active=True).order_by("name")
