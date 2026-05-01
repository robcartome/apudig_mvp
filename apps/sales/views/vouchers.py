"""
sales/views/vouchers.py — Vistas del ciclo de comprobantes.

Rutas:
  voucher_list      GET      /ventas/comprobantes/
  voucher_create    GET+POST /ventas/comprobantes/nuevo/
  voucher_from_ord  POST     /ventas/ordenes/<uuid:pk>/emitir/
  voucher_detail    GET      /ventas/comprobantes/<uuid:pk>/
  voucher_issue     POST     /ventas/comprobantes/<uuid:pk>/emitir/
  voucher_void      POST     /ventas/comprobantes/<uuid:pk>/anular/
  voucher_cancel    POST     /ventas/comprobantes/<uuid:pk>/cancelar/
  voucher_credit    GET+POST /ventas/comprobantes/<uuid:pk>/nota-credito/
  voucher_pdf       GET      /ventas/comprobantes/<uuid:pk>/pdf/
"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.sales.forms import (
    CreditNoteReasonForm,
    VoucherHeaderForm,
    VoucherLineFormSet,
)
from apps.sales.models import (
    DocumentSeries,
    SaleOrder,
    Voucher,
    VOUCHER_STATUS_CHOICES,
)
from apps.sales.selectors import get_voucher_detail, search_vouchers, get_series_for_store
from apps.sales.services import (
    cancel_voucher,
    create_credit_note,
    create_voucher_draft,
    issue_voucher,
    void_voucher,
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
    return [
        form.cleaned_data
        for form in formset
        if form.cleaned_data and not form.cleaned_data.get("DELETE")
    ]


# ── Vistas ────────────────────────────────────────────────────────────────────

def voucher_list(request):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    _, store_id = _get_ids(request)
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    voucher_type = request.GET.get("voucher_type", "")

    qs = search_vouchers(store_id, query=q or None, status=status or None)
    if voucher_type:
        qs = qs.filter(voucher_type=voucher_type)

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "sales/voucher_list.html", {
        "page_obj": page,
        "q": q,
        "status": status,
        "voucher_type": voucher_type,
        "status_choices": VOUCHER_STATUS_CHOICES,
    })


def voucher_create(request):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    company_id, store_id = _get_ids(request)
    # Determine voucher_type from query param (default factura)
    vtype = request.GET.get("voucher_type", "01")

    if request.method == "POST":
        vtype = request.POST.get("voucher_type", "01")
        header_form = VoucherHeaderForm(
            request.POST, company_id=company_id, store_id=store_id, voucher_type=vtype
        )
        line_formset = VoucherLineFormSet(request.POST, prefix="lines")

        if header_form.is_valid() and line_formset.is_valid():
            lines = _lines_from_formset(line_formset)
            if not lines:
                messages.error(request, "El comprobante debe tener al menos una línea.")
            else:
                cd = header_form.cleaned_data
                try:
                    voucher = create_voucher_draft(
                        store_id=str(cd["store"].pk),
                        customer=cd["customer"],
                        voucher_type=cd["voucher_type"],
                        series=cd["series"],
                        lines=lines,
                        created_by=request.user,
                        issue_date=cd["issue_date"],
                        currency=cd.get("currency", "PEN"),
                        notes=cd.get("notes", ""),
                    )
                    messages.success(request, "Comprobante en borrador creado.")
                    return redirect("sales:voucher_detail", pk=voucher.pk)
                except ValueError as exc:
                    messages.error(request, str(exc))
    else:
        header_form = VoucherHeaderForm(
            company_id=company_id, store_id=store_id, voucher_type=vtype,
            initial={"voucher_type": vtype},
        )
        line_formset = VoucherLineFormSet(prefix="lines")

    return render(request, "sales/voucher_form.html", {
        "header_form": header_form,
        "line_formset": line_formset,
        "title": "Nuevo comprobante",
    })


def voucher_from_ord(request, pk):
    """Crea borrador de comprobante a partir de una orden CONFIRMED."""
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    if request.method != "POST":
        return redirect("sales:order_detail", pk=pk)

    company_id, store_id = _get_ids(request)
    order = get_object_or_404(SaleOrder, pk=pk)

    series_id = request.POST.get("series_id")
    voucher_type = request.POST.get("voucher_type", "01")

    if not series_id:
        messages.error(request, "Debe seleccionar una serie.")
        return redirect("sales:order_detail", pk=pk)

    try:
        series = DocumentSeries.objects.get(pk=series_id)
        lines = [
            {
                "product": line.product,
                "description": line.description,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "unit_code": line.unit_code,
                "discount_amount": line.discount_amount,
                "tax_type": line.tax_type,
                "igv_rate": line.igv_rate,
                "sunat_product_code": line.sunat_product_code,
                "product_code": line.product_code,
            }
            for line in order.lines.all()
        ]
        voucher = create_voucher_draft(
            store_id=str(order.store_id) if order.store_id else None,
            customer=order.customer,
            voucher_type=voucher_type,
            series=series,
            lines=lines,
            sale_order=order,
            created_by=request.user,
            issue_date=timezone.now().date(),
            currency=order.currency,
            notes=order.notes,
        )
        messages.success(request, "Borrador de comprobante creado.")
        return redirect("sales:voucher_detail", pk=voucher.pk)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("sales:order_detail", pk=pk)


def voucher_detail(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    try:
        voucher = get_voucher_detail(pk)
    except Voucher.DoesNotExist:
        raise Http404

    company_id, store_id = _get_ids(request)
    # Pass available series for credit note quick-form
    cn_series = get_series_for_store(company_id, store_id, voucher_type="07") if company_id and store_id else []

    return render(request, "sales/voucher_detail.html", {
        "voucher": voucher,
        "cn_series": cn_series,
    })


def voucher_issue(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp
    if request.method != "POST":
        return redirect("sales:voucher_detail", pk=pk)
    try:
        v = issue_voucher(pk)
        messages.success(request, f"Comprobante {v.series_code}-{v.number} emitido.")
    except (Voucher.DoesNotExist, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("sales:voucher_detail", pk=pk)


def voucher_void(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp
    if request.method != "POST":
        return redirect("sales:voucher_detail", pk=pk)
    reason = request.POST.get("reason", "")
    try:
        void_voucher(pk, reason=reason)
        messages.success(request, "Comprobante anulado.")
    except (Voucher.DoesNotExist, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("sales:voucher_detail", pk=pk)


def voucher_cancel(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp
    if request.method != "POST":
        return redirect("sales:voucher_detail", pk=pk)
    try:
        cancel_voucher(pk)
        messages.success(request, "Comprobante cancelado.")
    except (Voucher.DoesNotExist, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("sales:voucher_detail", pk=pk)


def voucher_credit(request, pk):
    """Genera una nota de crédito a partir de un comprobante ISSUED."""
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    company_id, store_id = _get_ids(request)
    voucher = get_object_or_404(Voucher, pk=pk)

    if request.method == "POST":
        form = CreditNoteReasonForm(request.POST, company_id=company_id, store_id=store_id)
        if form.is_valid():
            cd = form.cleaned_data
            try:
                note = create_credit_note(
                    voucher_id=pk,
                    reason_code=cd["reason_code"],
                    reason_description=cd["reason_description"],
                    series=cd["series"],
                    created_by=request.user,
                )
                messages.success(request, "Nota de crédito creada.")
                return redirect("sales:voucher_detail", pk=note.pk)
            except ValueError as exc:
                messages.error(request, str(exc))
    else:
        form = CreditNoteReasonForm(company_id=company_id, store_id=store_id)

    return render(request, "sales/voucher_credit_form.html", {
        "form": form,
        "voucher": voucher,
    })


def voucher_pdf(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp
    try:
        voucher = get_voucher_detail(pk)
    except Voucher.DoesNotExist:
        raise Http404
    company = voucher.store.company if voucher.store else None
    return render(request, "sales/pdf/voucher_pdf.html", {"voucher": voucher, "company": company})
