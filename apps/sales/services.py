"""
sales/services.py — Lógica de negocio del ciclo comercial.

Flujo principal: SalesQuotation → SaleOrder → Voucher

Reglas:
- Toda creación de documento usa transaction.atomic().
- La numeración de series se hace con select_for_update() para evitar duplicados.
- Los snapshots del cliente (document_number, legal_name, etc.) se copian al
  momento de la creación; nunca se leen del cliente en tiempo de consulta.
"""
from django.db import transaction

from .models import DocumentSeries, SalesQuotation, SaleOrder, Voucher


def _next_series_number(series: DocumentSeries) -> int:
    """
    Obtiene y reserva el siguiente número de la serie con bloqueo optimista.
    Siempre llamar dentro de transaction.atomic().
    """
    locked = DocumentSeries.objects.select_for_update().get(pk=series.pk)
    locked.current_number += 1
    locked.save(update_fields=["current_number"])
    return locked.current_number


def get_or_create_series(company_id: str, store_id: str | None, voucher_type: str, series_code: str) -> DocumentSeries:
    obj, _ = DocumentSeries.objects.get_or_create(
        company_id=company_id,
        store_id=store_id,
        voucher_type=voucher_type,
        series=series_code,
    )
    return obj


@transaction.atomic
def create_quotation(store_id: str, customer, series: DocumentSeries, lines: list[dict], created_by=None, **kwargs) -> SalesQuotation:
    """
    Crea una cotización y asigna número de serie.
    lines: lista de dict con claves requeridas por SalesQuotationLine.
    """
    number = _next_series_number(series)
    quotation = SalesQuotation.objects.create(
        store_id=store_id,
        customer=customer,
        customer_document_type=customer.document_type,
        customer_document_number=customer.document_number,
        customer_legal_name=customer.legal_name,
        customer_address=customer.address,
        customer_ubigeo=customer.ubigeo,
        series=series,
        series_code=series.series,
        number=number,
        created_by=created_by,
        **kwargs,
    )
    for line in lines:
        quotation.lines.create(**line)
    return quotation
