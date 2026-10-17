"""Impresión y exportación de cotizaciones."""
from io import BytesIO

from django.http import Http404, HttpResponse
from django.urls import reverse
from django.utils.text import slugify

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from apps.sales.models import SalesQuotation
from apps.sales.printing import (
    CommercialPrintDocument,
    commercial_pdf_response,
    render_commercial_print,
)
from apps.sales.selectors import get_quotation_detail, search_quotations
from apps.core.list_filters import read_list_filters


def _require_auth(request):
    if not request.user.is_authenticated:
        from django.shortcuts import redirect
        return redirect("login")
    return None


def _quotation_for_print(request, pk):
    store_id = getattr(request, "active_store_id", None) or request.session.get("active_store_id")
    try:
        quotation = get_quotation_detail(pk)
    except SalesQuotation.DoesNotExist:
        raise Http404
    if not store_id or str(quotation.store_id) != str(store_id):
        raise Http404
    return quotation


def quotation_print(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    quotation = _quotation_for_print(request, pk)
    return render_commercial_print(
        request,
        CommercialPrintDocument(quotation, "quotation"),
        back_url=reverse("sales:quotation_detail", args=[quotation.pk]),
        pdf_url=reverse("sales:quotation_pdf", args=[quotation.pk]),
    )


def quotation_pdf(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    quotation = _quotation_for_print(request, pk)
    return commercial_pdf_response(
        request, CommercialPrintDocument(quotation, "quotation")
    )


def quotation_xlsx(request):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    company_id = getattr(request, "active_company_id", None) or request.session.get("active_company_id")
    store_id = getattr(request, "active_store_id", None) or request.session.get("active_store_id")
    filters = read_list_filters(request)
    qs = search_quotations(
        store_id, query=filters["q"] or None, status=filters["status"] or None,
        date_from=filters["date_from_value"], date_to=filters["date_to_value"],
        created_from=filters["created_from_value"], created_to=filters["created_to_value"],
        number=filters["number"] or None, series=filters["series"] or None,
        customer=filters["party"] or None, total_min=filters["total_min_value"],
        total_max=filters["total_max_value"],
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Cotizaciones"

    headers = [
        "Fecha emisión",
        "Serie",
        "Número",
        "Cliente",
        "Forma de pago",
        "Medio de pago",
        "Válido hasta",
        "Moneda",
        "Total",
        "Estado",
    ]
    ws.append(headers)

    header_fill = PatternFill("solid", fgColor="1F3C88")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    for quotation in qs:
        ws.append([
            quotation.issue_date,
            quotation.series_code,
            quotation.number,
            quotation.customer_legal_name,
            str(quotation.payment_method) if quotation.payment_method else "",
            str(quotation.means_of_payment) if quotation.means_of_payment else "",
            quotation.valid_until,
            quotation.currency,
            float(quotation.total),
            quotation.get_status_display(),
        ])

    for column_cells in ws.columns:
        max_len = 0
        column_letter = column_cells[0].column_letter
        for cell in column_cells:
            value = "" if cell.value is None else str(cell.value)
            max_len = max(max_len, len(value))
        ws.column_dimensions[column_letter].width = min(max_len + 2, 35)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"cotizaciones_{slugify(query) if query else 'lista'}.xlsx"
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
