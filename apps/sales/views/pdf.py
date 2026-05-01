"""
sales/views/pdf.py — Vista PDF de cotizaciones (HTML print-ready).

Genera una página HTML sin el layout base, optimizada para impresión A4.
El navegador la puede imprimir como PDF con Ctrl+P / window.print().
"""
from django.http import Http404
from django.shortcuts import render

from apps.sales.models import SalesQuotation
from apps.sales.selectors import get_quotation_detail


def _require_auth(request):
    if not request.user.is_authenticated:
        from django.shortcuts import redirect
        return redirect("login")
    return None


def quotation_pdf(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    try:
        quotation = get_quotation_detail(pk)
    except SalesQuotation.DoesNotExist:
        raise Http404

    # Obtener la empresa/compañía para el encabezado del PDF
    company = None
    if quotation.store:
        company = quotation.store.company

    return render(request, "sales/pdf/quotation_pdf.html", {
        "quotation": quotation,
        "company": company,
    })
