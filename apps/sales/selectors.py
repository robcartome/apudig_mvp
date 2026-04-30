"""
sales/selectors.py — Consultas de lectura del módulo de ventas.
"""
from .models import BusinessDocumentType, DocumentSeries, SalesQuotation, SaleOrder, Voucher


def get_quotations_for_store(store_id: str, status: str | None = None):
    qs = (
        SalesQuotation.objects
        .select_related("customer", "series")
        .filter(store_id=store_id)
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    return qs


def get_sale_orders_for_store(store_id: str, status: str | None = None):
    qs = (
        SaleOrder.objects
        .select_related("customer", "document_type")
        .filter(store_id=store_id)
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    return qs


def get_series_for_store(company_id: str, store_id: str, voucher_type: str | None = None):
    qs = DocumentSeries.objects.filter(
        company_id=company_id,
        store_id=store_id,
        active=True,
    )
    if voucher_type:
        qs = qs.filter(voucher_type=voucher_type)
    return qs


def get_active_document_types():
    return BusinessDocumentType.objects.filter(active=True).order_by("code")
