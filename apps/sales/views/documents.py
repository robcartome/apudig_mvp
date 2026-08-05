"""
sales/views/documents.py — Vistas del ciclo de documentos de venta.

Rutas:
  document_list      GET      /ventas/comprobantes/
  document_create    GET+POST /ventas/comprobantes/nuevo/
  document_from_order  POST     /ventas/ordenes/<uuid:pk>/emitir/
  document_detail    GET      /ventas/comprobantes/<uuid:pk>/
  document_issue     POST     /ventas/comprobantes/<uuid:pk>/emitir/
  document_void      POST     /ventas/comprobantes/<uuid:pk>/anular/
  document_cancel    POST     /ventas/comprobantes/<uuid:pk>/cancelar/
  document_credit    GET+POST /ventas/comprobantes/<uuid:pk>/nota-credito/
  document_pdf       GET      /ventas/comprobantes/<uuid:pk>/pdf/
"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.sales.forms import (
    CreditNoteReasonForm,
    SalesDocumentHeaderForm,
    SalesDocumentLineFormSet,
)
from apps.sales.models import (
    DocumentSeries,
    SaleOrder,
    SalesDocument,
    SALES_DOCUMENT_STATUS_CHOICES,
)
from apps.sales.selectors import get_document_detail, search_sales_documents, get_series_for_store
from apps.sales.services import (
    cancel_sales_document,
    create_credit_note,
    create_sales_document_draft,
    issue_sales_document,
    void_sales_document,
)
from apps.inventory.models import PriceList

DEFAULT_IGV_RATE = 18


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
        if form.cleaned_data
        and not form.cleaned_data.get("DELETE")
        and form.cleaned_data.get("product")   # ignorar filas extra vacías
    ]


# ── Vistas ────────────────────────────────────────────────────────────────────

def document_list(request):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    _, store_id = _get_ids(request)
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    document_type = request.GET.get("document_type", "")

    qs = search_sales_documents(store_id, query=q or None, status=status or None)
    if document_type:
        qs = qs.filter(document_type=document_type)

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "sales/document_list.html", {
        "page_obj": page,
        "q": q,
        "status": status,
        "document_type": document_type,
        "status_choices": SALES_DOCUMENT_STATUS_CHOICES,
    })


def document_create(request):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    company_id, store_id = _get_ids(request)
    # Determine document_type from query param (default factura)
    vtype = request.GET.get("document_type", "01")

    if request.method == "POST":
        vtype = request.POST.get("document_type", "01")
        header_form = SalesDocumentHeaderForm(
            request.POST, company_id=company_id, store_id=store_id, document_type=vtype
        )
        line_formset = SalesDocumentLineFormSet(request.POST, prefix="lines")

        if header_form.is_valid() and line_formset.is_valid():
            lines = _lines_from_formset(line_formset)
            if not lines:
                messages.error(request, "El comprobante debe tener al menos una línea.")
            else:
                cd = header_form.cleaned_data
                try:
                    sales_document = create_sales_document_draft(
                        store_id=str(cd["store"].pk),
                        customer=cd["customer"],
                        document_type=cd["document_type"],
                        series=cd["series"],
                        lines=lines,
                        created_by=request.user,
                        issue_date=cd["issue_date"],
                        currency=cd.get("currency", "PEN"),
                        notes=cd.get("notes", ""),
                    )
                    messages.success(request, "Comprobante en borrador creado.")
                    return redirect("sales:document_detail", pk=sales_document.pk)
                except ValueError as exc:
                    messages.error(request, str(exc))
    else:
        header_form = SalesDocumentHeaderForm(
            company_id=company_id, store_id=store_id, document_type=vtype,
            initial={"document_type": vtype},
        )
        line_formset = SalesDocumentLineFormSet(prefix="lines")

    return render(request, "sales/document_form.html", {
        "header_form": header_form,
        "line_formset": line_formset,
        "title": "Nuevo comprobante",
        "igv_rate": DEFAULT_IGV_RATE,
        "price_lists": PriceList.objects.filter(
            company_id=company_id, active=True
        ).order_by("name") if company_id else PriceList.objects.none(),
    })


def document_from_order(request, pk):
    """Crea borrador de comprobante a partir de una orden CONFIRMED."""
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    if request.method != "POST":
        return redirect("sales:order_detail", pk=pk)

    company_id, store_id = _get_ids(request)
    order = get_object_or_404(SaleOrder, pk=pk)

    series_id = request.POST.get("series_id")
    document_type = request.POST.get("document_type", "01")

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
        sales_document = create_sales_document_draft(
            store_id=str(order.store_id) if order.store_id else None,
            customer=order.customer,
            document_type=document_type,
            series=series,
            lines=lines,
            sale_order=order,
            created_by=request.user,
            issue_date=timezone.now().date(),
            currency=order.currency,
            notes=order.notes,
        )
        messages.success(request, "Borrador de comprobante creado.")
        return redirect("sales:document_detail", pk=sales_document.pk)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("sales:order_detail", pk=pk)


def document_detail(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    try:
        sales_document = get_document_detail(pk)
    except SalesDocument.DoesNotExist:
        raise Http404

    company_id, store_id = _get_ids(request)
    # Pass available series for credit note quick-form
    cn_series = get_series_for_store(company_id, store_id, document_type="07") if company_id and store_id else []

    return render(request, "sales/document_detail.html", {
        "sales_document": sales_document,
        "cn_series": cn_series,
    })


def document_issue(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp
    if request.method != "POST":
        return redirect("sales:document_detail", pk=pk)
    try:
        v = issue_sales_document(pk)
        messages.success(request, f"Comprobante {v.series_code}-{v.number} emitido.")
    except (SalesDocument.DoesNotExist, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("sales:document_detail", pk=pk)


def document_void(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp
    if request.method != "POST":
        return redirect("sales:document_detail", pk=pk)
    reason = request.POST.get("reason", "")
    try:
        void_sales_document(pk, reason=reason)
        messages.success(request, "Comprobante anulado.")
    except (SalesDocument.DoesNotExist, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("sales:document_detail", pk=pk)


def document_cancel(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp
    if request.method != "POST":
        return redirect("sales:document_detail", pk=pk)
    try:
        cancel_sales_document(pk)
        messages.success(request, "Comprobante cancelado.")
    except (SalesDocument.DoesNotExist, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("sales:document_detail", pk=pk)


def document_credit(request, pk):
    """Genera una nota de crédito a partir de un comprobante ISSUED."""
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    company_id, store_id = _get_ids(request)
    sales_document = get_object_or_404(SalesDocument, pk=pk)

    if request.method == "POST":
        form = CreditNoteReasonForm(request.POST, company_id=company_id, store_id=store_id)
        if form.is_valid():
            cd = form.cleaned_data
            try:
                note = create_credit_note(
                    sales_document_id=pk,
                    reason_code=cd["reason_code"],
                    reason_description=cd["reason_description"],
                    series=cd["series"],
                    created_by=request.user,
                )
                messages.success(request, "Nota de crédito creada.")
                return redirect("sales:document_detail", pk=note.pk)
            except ValueError as exc:
                messages.error(request, str(exc))
    else:
        form = CreditNoteReasonForm(company_id=company_id, store_id=store_id)

    return render(request, "sales/document_credit_form.html", {
        "form": form,
        "sales_document": sales_document,
    })


def document_pdf(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp
    try:
        sales_document = get_document_detail(pk)
    except SalesDocument.DoesNotExist:
        raise Http404
    company = sales_document.store.company if sales_document.store else None
    return render(request, "sales/pdf/document_pdf.html", {"sales_document": sales_document, "company": company})
