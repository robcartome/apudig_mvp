"""
sales/selectors.py — Consultas de lectura del módulo de ventas.
"""
from django.db.models import Prefetch, Q

from apps.partners.models import DocumentType
from .models import DocumentSeries, SalesQuotation, SaleOrder, SalesDocument


def get_dashboard_sales(company_id, store_id, start, end, previous_start, currency):
    """Daily net sales; consolidated POS invoices must not count tickets twice."""
    from decimal import Decimal
    from django.db.models import Case, Count, DecimalField, F, Sum, When
    from django.db.models.functions import TruncDate

    documents = SalesDocument.objects.filter(
        store_id=store_id, store__company_id=company_id, currency=currency,
    )
    issued = documents.filter(
        status__in=("ISSUED", "SUNAT_PENDING", "SUNAT_ACCEPTED", "SUNAT_OBSERVED"),
        document_type__code__in=("NV", "01", "03", "07", "08"),
        source_document_links__isnull=True,
    ).annotate(net_amount=Case(
        When(document_type__code="07", then=-F("total")),
        default=F("total"), output_field=DecimalField(max_digits=18, decimal_places=2),
    ))
    current = issued.filter(issue_date__gte=start, issue_date__lt=end)
    totals = current.aggregate(total=Sum("net_amount"), count=Count("pk"))
    previous = issued.filter(issue_date__gte=previous_start, issue_date__lt=start).aggregate(
        total=Sum("net_amount")
    )["total"] or Decimal("0")
    daily = list(current.order_by().annotate(day=TruncDate("issue_date")).values("day").annotate(
        total=Sum("net_amount")
    ).order_by("day"))
    return {
        "total": totals["total"] or Decimal("0"), "count": totals["count"],
        "previous": previous, "daily": daily,
        "recent": list(current.select_related("document_type").order_by("-issue_date", "-created_at")[:5]),
        "drafts": documents.filter(status="DRAFT").count(),
        "quotations": SalesQuotation.objects.filter(
            store_id=store_id, store__company_id=company_id, status="SENT",
        ).count(),
        "orders": SaleOrder.objects.filter(
            store_id=store_id, store__company_id=company_id, status="CONFIRMED",
        ).count(),
    }


def with_document_payments(queryset):
    from apps.pos.models import SalesPayment

    return queryset.select_related("payment_method", "pos_transaction", "document_type").prefetch_related(
        Prefetch("pos_payments", queryset=SalesPayment.objects.select_related(
            "means_of_payment", "cash_session__register", "created_by"
        ).order_by("paid_at", "created_at", "pk"), to_attr="payment_history")
    )


def get_quotations_for_store(store_id: str, status: str | None = None):
    qs = (
        SalesQuotation.objects.for_store(store_id)
        .select_related("customer", "series", "payment_method", "means_of_payment")
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    return qs


def search_quotations(
    store_id: str, query: str | None = None, status: str | None = None, *,
    date_from=None, date_to=None, created_from=None, created_to=None,
    number=None, series=None, customer=None, total_min=None, total_max=None,
):
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
            | Q(number__icontains=query)
        )
    return _filter_commercial_queryset(
        qs, date_from=date_from, date_to=date_to,
        created_from=created_from, created_to=created_to,
        number=number, series=series, party=customer,
        total_min=total_min, total_max=total_max,
    )


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


def search_orders(
    store_id: str, query: str | None = None, status: str | None = None, *,
    date_from=None, date_to=None, created_from=None, created_to=None,
    number=None, series=None, customer=None, total_min=None, total_max=None,
):
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
    return _filter_commercial_queryset(
        qs, date_from=date_from, date_to=date_to,
        created_from=created_from, created_to=created_to,
        number=number, series=series, party=customer,
        total_min=total_min, total_max=total_max,
    )


def _filter_commercial_queryset(
    qs, *, date_from=None, date_to=None, created_from=None, created_to=None,
    number=None, series=None, party=None, total_min=None, total_max=None,
):
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
    if party:
        qs = qs.filter(
            Q(customer_legal_name__icontains=party)
            | Q(customer_document_number__icontains=party)
        )
    if total_min is not None:
        qs = qs.filter(total__gte=total_min)
    if total_max is not None:
        qs = qs.filter(total__lte=total_max)
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
        .select_related("customer", "series", "document_type", "pos_transaction__register")
        .order_by("-issue_date", "-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    return qs


def search_sales_documents(
    store_id: str, query: str | None = None, status: str | None = None, *,
    date_from=None, date_to=None, created_from=None, created_to=None,
    number=None, series=None, customer=None, customer_id=None, total_min=None,
    total_max=None,
):
    qs = (
        SalesDocument.objects.for_store(store_id)
        .select_related("customer", "series", "document_type", "pos_transaction__register")
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
        qs = qs.filter(issue_date__date__gte=date_from)
    if date_to:
        qs = qs.filter(issue_date__date__lte=date_to)
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
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
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
            "warehouse", "pos_transaction__register",
        )
        .prefetch_related(
            "lines__product__unit", "lines__unit",
            "inventory_movements__warehouse", "inventory_movements__document_type",
        )
    )
    if store_id is not None:
        queryset = queryset.filter(store_id=store_id)
    return with_document_payments(queryset).get(pk=pk)
