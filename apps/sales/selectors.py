"""
sales/selectors.py — Consultas de lectura del módulo de ventas.
"""
from django.db.models import Q

from apps.partners.models import DocumentType
from .models import DocumentSeries, SalesQuotation, SaleOrder, SalesDocument

def get_quotations_for_store(store_id: str, status: str | None = None):
    qs = (
        SalesQuotation.objects.for_store(store_id)
        .select_related("customer", "series", "payment_method", "means_of_payment")
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
        SalesQuotation.objects.for_store(store_id)
        .select_related("customer", "series", "payment_method", "means_of_payment")
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
        .select_related("customer", "series", "store", "created_by", "payment_method", "means_of_payment")
        .prefetch_related("lines__product__unit", "lines__unit")
        .get(pk=pk)
    )


def get_sale_orders_for_store(store_id: str, status: str | None = None):
    qs = (
        SaleOrder.objects.for_store(store_id)
        .select_related("customer", "document_type", "series")
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    return qs


def search_orders(store_id: str, query: str | None = None, status: str | None = None):
    qs = (
        SaleOrder.objects.for_store(store_id)
        .select_related("customer", "document_type", "series")
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
        .prefetch_related("lines__product__unit", "lines__unit")
        .get(pk=pk)
    )


def get_series_for_store(company_id: str, store_id: str, document_type: str | None = None):
    qs = DocumentSeries.objects.for_company(company_id).for_store(store_id).filter(active=True)
    if document_type:
        qs = qs.filter(document_type__code=document_type)
    return qs


def get_active_document_types():
    return DocumentType.objects.filter(active=True).order_by("code")


def get_sales_documents_for_store(store_id: str, status: str | None = None):
    qs = (
        SalesDocument.objects.for_store(store_id)
        .select_related("customer", "series", "document_type")
        .order_by("-issue_date", "-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    return qs


def search_sales_documents(
    store_id: str, query: str | None = None, status: str | None = None, *,
    date_from=None, date_to=None, created_from=None, created_to=None,
    number=None, series=None, customer=None, total_min=None, total_max=None,
):
    qs = (
        SalesDocument.objects.for_store(store_id)
        .select_related("customer", "series", "document_type")
        .order_by("-issue_date", "-created_at")
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
    if date_from:
        qs = qs.filter(issue_date__gte=date_from)
    if date_to:
        qs = qs.filter(issue_date__lte=date_to)
    if created_from:
        qs = qs.filter(created_at__date__gte=created_from)
    if created_to:
        qs = qs.filter(created_at__date__lte=created_to)
    if number:
        qs = qs.filter(number__icontains=number)
    if series:
        qs = qs.filter(series_code__icontains=series)
    if customer:
        qs = qs.filter(
            Q(customer_legal_name__icontains=customer)
            | Q(customer_document_number__icontains=customer)
        )
    if total_min is not None:
        qs = qs.filter(total__gte=total_min)
    if total_max is not None:
        qs = qs.filter(total__lte=total_max)
    return qs


def get_document_detail(pk, store_id=None):
    """Retorna SalesDocument con líneas y producto prefetcheados."""
    queryset = (
        SalesDocument.objects
        .select_related(
            "customer", "series", "document_type", "store", "created_by",
            "sale_order", "reference_document", "source_quotation",
            "payment_method", "means_of_payment", "seller", "price_list",
            "warehouse", "inventory_movement",
        )
        .prefetch_related("lines__product__unit", "lines__unit")
    )
    if store_id is not None:
        queryset = queryset.filter(store_id=store_id)
    return queryset.get(pk=pk)
