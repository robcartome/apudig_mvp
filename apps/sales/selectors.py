"""
sales/selectors.py — Consultas de lectura del módulo de ventas.
"""
from django.db.models import Q

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


def search_quotations(store_id: str, query: str | None = None, status: str | None = None):
    """
    Búsqueda de cotizaciones por texto (nombre cliente, nº cotización) y/o estado.
    """
    qs = (
        SalesQuotation.objects
        .select_related("customer", "series")
        .filter(store_id=store_id)
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    if query:
        qs = qs.filter(
            Q(customer_legal_name__icontains=query)
            | Q(customer_document_number__icontains=query)
            | Q(series_code__icontains=query)
        )
    return qs


def get_quotation_detail(pk):
    """Retorna SalesQuotation con líneas y producto prefetcheados."""
    return (
        SalesQuotation.objects
        .select_related("customer", "series", "store", "created_by")
        .prefetch_related("lines__product__unit")
        .get(pk=pk)
    )


def get_sale_orders_for_store(store_id: str, status: str | None = None):
    qs = (
        SaleOrder.objects
        .select_related("customer", "document_type", "series")
        .filter(store_id=store_id)
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    return qs


def search_orders(store_id: str, query: str | None = None, status: str | None = None):
    qs = (
        SaleOrder.objects
        .select_related("customer", "document_type", "series")
        .filter(store_id=store_id)
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    if query:
        qs = qs.filter(
            Q(customer_legal_name__icontains=query)
            | Q(customer_document_number__icontains=query)
            | Q(series_code__icontains=query)
            | Q(number__icontains=query)
        )
    return qs


def get_order_detail(pk):
    """Retorna SaleOrder con líneas y producto prefetcheados."""
    return (
        SaleOrder.objects
        .select_related("customer", "document_type", "series", "store", "created_by", "quotation")
        .prefetch_related("lines__product__unit")
        .get(pk=pk)
    )


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
