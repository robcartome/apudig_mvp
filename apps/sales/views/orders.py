"""
sales/views/orders.py — Vistas del ciclo de órdenes de venta.

Rutas:
  order_list        GET      /ventas/ordenes/
  order_create      GET+POST /ventas/ordenes/nueva/
  order_from_quot   POST     /ventas/cotizaciones/<uuid:pk>/crear-orden/
  order_detail      GET      /ventas/ordenes/<uuid:pk>/
  order_update      GET+POST /ventas/ordenes/<uuid:pk>/editar/   (solo DRAFT)
  order_confirm     POST     /ventas/ordenes/<uuid:pk>/confirmar/
  order_cancel      POST     /ventas/ordenes/<uuid:pk>/cancelar/
  order_pdf         GET      /ventas/ordenes/<uuid:pk>/pdf/
"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.sales.forms import SaleOrderHeaderForm, SaleOrderLineFormSet
from apps.sales.models import SaleOrder, SALE_ORDER_STATUS_CHOICES, SalesQuotation
from apps.sales.selectors import search_orders, get_order_detail, get_series_for_store
from apps.sales.services import (
    cancel_order,
    confirm_order,
    create_order_from_quotation,
    create_sale_order,
    update_sale_order,
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

def order_list(request):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    _, store_id = _get_ids(request)
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")

    orders = search_orders(store_id, query=q or None, status=status or None)
    paginator = Paginator(orders, 25)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "sales/order_list.html", {
        "page_obj": page,
        "q": q,
        "status": status,
        "status_choices": SALE_ORDER_STATUS_CHOICES,
    })


def order_create(request):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    company_id, store_id = _get_ids(request)

    if request.method == "POST":
        header_form = SaleOrderHeaderForm(request.POST, company_id=company_id, store_id=store_id)
        line_formset = SaleOrderLineFormSet(request.POST, prefix="lines")

        if header_form.is_valid() and line_formset.is_valid():
            lines = _lines_from_formset(line_formset)
            if not lines:
                messages.error(request, "La orden debe tener al menos una línea.")
            else:
                cd = header_form.cleaned_data
                try:
                    order = create_sale_order(
                        store_id=str(cd["store"].pk),
                        customer=cd["customer"],
                        document_type=cd["document_type"],
                        series=cd["series"],
                        lines=lines,
                        created_by=request.user,
                        issue_date=cd["issue_date"],
                        due_date=cd.get("due_date"),
                        currency=cd.get("currency", "PEN"),
                        payment_term_days=cd.get("payment_term_days", 0),
                        notes=cd.get("notes", ""),
                        internal_reference=cd.get("internal_reference", ""),
                    )
                    messages.success(request, f"Orden {order.series_code}-{order.number} creada.")
                    return redirect("sales:order_detail", pk=order.pk)
                except ValueError as exc:
                    messages.error(request, str(exc))
    else:
        header_form = SaleOrderHeaderForm(company_id=company_id, store_id=store_id)
        line_formset = SaleOrderLineFormSet(prefix="lines")

    return render(request, "sales/order_form.html", {
        "header_form": header_form,
        "line_formset": line_formset,
        "title": "Nueva orden de venta",
    })


def order_from_quot(request, pk):
    """Convierte una cotización APPROVED en orden de venta."""
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    if request.method != "POST":
        return redirect("sales:quotation_detail", pk=pk)

    company_id, store_id = _get_ids(request)
    quotation = get_object_or_404(SalesQuotation, pk=pk)

    document_type_id = request.POST.get("document_type_id")
    series_id = request.POST.get("series_id")

    if not document_type_id or not series_id:
        messages.error(request, "Debe seleccionar tipo de documento y serie.")
        return redirect("sales:quotation_detail", pk=pk)

    from apps.sales.models import BusinessDocumentType, DocumentSeries

    try:
        doc_type = BusinessDocumentType.objects.get(pk=document_type_id)
        series = DocumentSeries.objects.get(pk=series_id)
        order = create_order_from_quotation(
            quotation_id=quotation.pk,
            document_type=doc_type,
            series=series,
            created_by=request.user,
        )
        messages.success(request, f"Orden {order.series_code}-{order.number} creada desde cotización.")
        return redirect("sales:order_detail", pk=order.pk)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("sales:quotation_detail", pk=pk)


def order_detail(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    _, store_id = _get_ids(request)
    try:
        order = get_order_detail(pk)
    except SaleOrder.DoesNotExist:
        raise Http404

    # Series OV disponibles para el formulario de conversión (si aplica)
    return render(request, "sales/order_detail.html", {"order": order})


def order_update(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    company_id, store_id = _get_ids(request)
    order = get_object_or_404(SaleOrder, pk=pk, store_id=store_id)

    if order.status != "DRAFT":
        messages.error(request, "Solo se pueden editar órdenes en estado Borrador.")
        return redirect("sales:order_detail", pk=pk)

    if request.method == "POST":
        header_form = SaleOrderHeaderForm(request.POST, instance=order, company_id=company_id, store_id=store_id)
        line_formset = SaleOrderLineFormSet(request.POST, prefix="lines")

        if header_form.is_valid() and line_formset.is_valid():
            lines = _lines_from_formset(line_formset)
            if not lines:
                messages.error(request, "La orden debe tener al menos una línea.")
            else:
                cd = header_form.cleaned_data
                try:
                    update_sale_order(
                        order_id=pk,
                        lines=lines,
                        issue_date=cd["issue_date"],
                        due_date=cd.get("due_date"),
                        currency=cd.get("currency", "PEN"),
                        payment_term_days=cd.get("payment_term_days", 0),
                        notes=cd.get("notes", ""),
                        internal_reference=cd.get("internal_reference", ""),
                    )
                    messages.success(request, "Orden actualizada.")
                    return redirect("sales:order_detail", pk=pk)
                except ValueError as exc:
                    messages.error(request, str(exc))
    else:
        header_form = SaleOrderHeaderForm(instance=order, company_id=company_id, store_id=store_id)
        initial = [
            {
                "product": line.product,
                "description": line.description,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "discount_amount": line.discount_amount,
                "tax_type": line.tax_type,
                "igv_rate": line.igv_rate,
            }
            for line in order.lines.select_related("product").all()
        ]
        line_formset = SaleOrderLineFormSet(initial=initial, prefix="lines")

    return render(request, "sales/order_form.html", {
        "header_form": header_form,
        "line_formset": line_formset,
        "title": "Editar orden de venta",
        "order": order,
    })


def _order_transition(request, pk, service_fn, success_msg):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp
    if request.method != "POST":
        return redirect("sales:order_detail", pk=pk)
    try:
        service_fn(pk)
        messages.success(request, success_msg)
    except (SaleOrder.DoesNotExist, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("sales:order_detail", pk=pk)


def order_confirm(request, pk):
    return _order_transition(request, pk, confirm_order, "Orden confirmada.")


def order_cancel(request, pk):
    return _order_transition(request, pk, cancel_order, "Orden cancelada.")


def order_pdf(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp
    try:
        order = get_order_detail(pk)
    except SaleOrder.DoesNotExist:
        raise Http404
    company = order.store.company if order.store else None
    return render(request, "sales/pdf/order_pdf.html", {"order": order, "company": company})
