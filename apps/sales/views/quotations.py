"""
sales/views/quotations.py — Vistas del ciclo de cotizaciones.

Rutas:
  quotation_list    GET      /ventas/cotizaciones/
  quotation_create  GET+POST /ventas/cotizaciones/nueva/
  quotation_detail  GET      /ventas/cotizaciones/<uuid:pk>/
  quotation_update  GET+POST /ventas/cotizaciones/<uuid:pk>/editar/   (solo DRAFT)
  quotation_approve POST     /ventas/cotizaciones/<uuid:pk>/aprobar/
  quotation_reject  POST     /ventas/cotizaciones/<uuid:pk>/rechazar/
  quotation_cancel  POST     /ventas/cotizaciones/<uuid:pk>/cancelar/
"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.sales.forms import QuotationHeaderForm, QuotationLineFormSet
from apps.sales.models import SalesQuotation, QUOTATION_STATUS_CHOICES
from apps.sales.selectors import search_quotations, get_quotation_detail
from apps.sales.services import (
    approve_quotation,
    cancel_quotation,
    create_quotation,
    reject_quotation,
    update_quotation,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_auth(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return None


def _get_ids(request):
    company_id = getattr(request, "active_company_id", None) or request.session.get("active_company_id")
    store_id = getattr(request, "active_store_id", None) or request.session.get("active_store_id")
    return company_id, store_id


def _lines_from_formset(formset) -> list[dict]:
    lines = []
    for form in formset:
        if not form.cleaned_data or form.cleaned_data.get("DELETE"):
            continue
        lines.append(form.cleaned_data)
    return lines


# ── Vistas ────────────────────────────────────────────────────────────────────

def quotation_list(request):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    _, store_id = _get_ids(request)
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")

    qs = search_quotations(store_id, query=query or None, status=status or None)
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "sales/quotation_list.html", {
        "page_obj": page_obj,
        "query": query,
        "status": status,
        "status_choices": QUOTATION_STATUS_CHOICES,
    })


def quotation_create(request):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    company_id, store_id = _get_ids(request)

    if request.method == "POST":
        header_form = QuotationHeaderForm(request.POST, company_id=company_id, store_id=store_id)
        line_formset = QuotationLineFormSet(request.POST, prefix="lines")

        if header_form.is_valid() and line_formset.is_valid():
            lines = _lines_from_formset(line_formset)
            if not lines:
                messages.error(request, "La cotización debe tener al menos una línea.")
            else:
                cd = header_form.cleaned_data
                try:
                    q = create_quotation(
                        store_id=str(cd["store"].pk),
                        customer=cd["customer"],
                        series=cd["series"],
                        lines=lines,
                        created_by=request.user,
                        issue_date=cd["issue_date"],
                        valid_until=cd.get("valid_until"),
                        currency=cd.get("currency", "PEN"),
                        notes=cd.get("notes", ""),
                        internal_reference=cd.get("internal_reference", ""),
                    )
                    messages.success(request, f"Cotización {q.series_code}-{q.number:08d} creada.")
                    return redirect("sales:quotation_detail", pk=q.pk)
                except ValueError as exc:
                    messages.error(request, str(exc))
    else:
        header_form = QuotationHeaderForm(company_id=company_id, store_id=store_id)
        line_formset = QuotationLineFormSet(prefix="lines")

    return render(request, "sales/quotation_form.html", {
        "header_form": header_form,
        "line_formset": line_formset,
        "title": "Nueva cotización",
    })


def quotation_detail(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    _, store_id = _get_ids(request)
    try:
        quotation = get_quotation_detail(pk)
    except SalesQuotation.DoesNotExist:
        raise Http404

    return render(request, "sales/quotation_detail.html", {"quotation": quotation})


def quotation_update(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    company_id, store_id = _get_ids(request)
    quotation = get_object_or_404(SalesQuotation, pk=pk, store_id=store_id)

    if quotation.status != "DRAFT":
        messages.error(request, "Solo se pueden editar cotizaciones en estado Borrador.")
        return redirect("sales:quotation_detail", pk=pk)

    if request.method == "POST":
        header_form = QuotationHeaderForm(request.POST, instance=quotation, company_id=company_id, store_id=store_id)
        line_formset = QuotationLineFormSet(request.POST, prefix="lines")

        if header_form.is_valid() and line_formset.is_valid():
            lines = _lines_from_formset(line_formset)
            if not lines:
                messages.error(request, "La cotización debe tener al menos una línea.")
            else:
                cd = header_form.cleaned_data
                try:
                    update_quotation(
                        quotation_id=pk,
                        lines=lines,
                        issue_date=cd["issue_date"],
                        valid_until=cd.get("valid_until"),
                        currency=cd.get("currency", "PEN"),
                        notes=cd.get("notes", ""),
                        internal_reference=cd.get("internal_reference", ""),
                    )
                    messages.success(request, "Cotización actualizada.")
                    return redirect("sales:quotation_detail", pk=pk)
                except ValueError as exc:
                    messages.error(request, str(exc))
    else:
        header_form = QuotationHeaderForm(instance=quotation, company_id=company_id, store_id=store_id)
        initial = [
            {
                "product": line.product,
                "description": line.description,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "discount_amount": line.discount_amount,
                "tax_type": line.tax_type,
                "igv_rate": line.igv_rate,
                "memo": line.memo,
            }
            for line in quotation.lines.select_related("product").all()
        ]
        line_formset = QuotationLineFormSet(initial=initial, prefix="lines")

    return render(request, "sales/quotation_form.html", {
        "header_form": header_form,
        "line_formset": line_formset,
        "title": "Editar cotización",
        "quotation": quotation,
    })


# ── Transiciones de estado ────────────────────────────────────────────────────

def _status_transition(request, pk, service_fn, success_msg):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    if request.method != "POST":
        return redirect("sales:quotation_detail", pk=pk)

    try:
        service_fn(pk)
        messages.success(request, success_msg)
    except (ValueError, SalesQuotation.DoesNotExist) as exc:
        messages.error(request, str(exc))
    return redirect("sales:quotation_detail", pk=pk)


def quotation_approve(request, pk):
    return _status_transition(request, pk, approve_quotation, "Cotización aprobada.")


def quotation_reject(request, pk):
    return _status_transition(request, pk, reject_quotation, "Cotización rechazada.")


def quotation_cancel(request, pk):
    return _status_transition(request, pk, cancel_quotation, "Cotización cancelada.")
