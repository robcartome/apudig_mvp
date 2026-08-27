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
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.sales.forms import (
    CreditNoteReasonForm,
    SalesDocumentHeaderForm,
    SalesDocumentLineFormSet,
)
from apps.sales.models import (
    DocumentSeries,
    SaleOrder,
    SalesDocument,
    SalesQuotation,
    SALES_DOCUMENT_STATUS_CHOICES,
)
from apps.sales.selectors import get_document_detail, search_sales_documents, get_series_for_store
from apps.sales.services import (
    cancel_sales_document,
    copy_sales_document,
    create_credit_note,
    create_document_from_quotation,
    create_sales_document_draft,
    delete_sales_document_draft,
    issue_sales_document,
    update_sales_document_draft,
    void_sales_document,
)
from apps.inventory.models import PriceList, Warehouse
from apps.partners.models import DocumentType
from apps.core.models import AuditLog
from apps.users.permissions import user_has_company_permission

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


def _require_document_permission(request, action):
    redirect_response = _require_auth(request)
    if redirect_response:
        return redirect_response
    company_id, _ = _get_ids(request)
    if not user_has_company_permission(
        request.user, company_id, f"{action}.sales.documents"
    ):
        return HttpResponseForbidden(
            "No tienes permiso para realizar esta acción sobre documentos de venta."
        )
    return None


def _document_permissions_context(request):
    company_id, _ = _get_ids(request)
    return {
        "can_manage_sales_documents": user_has_company_permission(
            request.user, company_id, "manage.sales.documents"
        ),
        "can_authorize_sales_documents": user_has_company_permission(
            request.user, company_id, "authorize.sales.documents"
        ),
    }


def _lines_from_formset(formset) -> list[dict]:
    return [
        form.cleaned_data
        for form in formset
        if form.cleaned_data
        and not form.cleaned_data.get("DELETE")
        and form.cleaned_data.get("product")   # ignorar filas extra vacías
    ]


def _document_form_context(company_id, header_form, line_formset, title, document=None):
    return {
        "header_form": header_form,
        "line_formset": line_formset,
        "title": title,
        "sales_document": document,
        "igv_rate": DEFAULT_IGV_RATE,
        "price_lists": PriceList.objects.filter(
            company_id=company_id, active=True
        ).order_by("name") if company_id else PriceList.objects.none(),
    }


def _document_service_fields(cleaned_data):
    return {
        "issue_date": cleaned_data["issue_date"],
        "currency": cleaned_data.get("currency", "PEN"),
        "exchange_rate": cleaned_data.get("exchange_rate") or 1,
        "payment_method": cleaned_data.get("payment_method"),
        "means_of_payment": cleaned_data.get("means_of_payment"),
        "seller": cleaned_data.get("seller"),
        "price_list": cleaned_data.get("price_list"),
        "register_inventory_movement": cleaned_data.get("register_inventory_movement", False),
        "warehouse": cleaned_data.get("warehouse"),
        "notes": cleaned_data.get("notes", ""),
        "internal_reference": cleaned_data.get("internal_reference", ""),
        "number": cleaned_data.get("number", "") if cleaned_data.get("manual_number") else "",
    }


# ── Vistas ────────────────────────────────────────────────────────────────────

def document_list(request):
    redirect_resp = _require_document_permission(request, "read")
    if redirect_resp:
        return redirect_resp

    _, store_id = _get_ids(request)
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    document_type = request.GET.get("document_type", "")

    qs = search_sales_documents(store_id, query=q or None, status=status or None)
    if document_type:
        qs = qs.filter(document_type__code=document_type)

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page,
        "q": q,
        "status": status,
        "document_type": document_type,
        "status_choices": SALES_DOCUMENT_STATUS_CHOICES,
        "document_types": DocumentType.objects.filter(
            active=True, category__in=("SALES", "BILLING")
        ).order_by("code"),
        **_document_permissions_context(request),
    }
    return render(request, "sales/document_list.html", context)


def document_create(request):
    redirect_resp = _require_document_permission(request, "manage")
    if redirect_resp:
        return redirect_resp

    company_id, store_id = _get_ids(request)
    document_type = request.GET.get("document_type", "NV")

    if request.method == "POST":
        document_type = request.POST.get("document_type", "NV")
        header_form = SalesDocumentHeaderForm(
            request.POST, company_id=company_id, store_id=store_id, document_type=document_type
        )
        line_formset = SalesDocumentLineFormSet(request.POST, prefix="lines")

        if header_form.is_valid() and line_formset.is_valid():
            lines = _lines_from_formset(line_formset)
            if not lines:
                messages.error(request, "El documento debe tener al menos una línea.")
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
                        **_document_service_fields(cd),
                    )
                    messages.success(request, "Documento de venta creado como borrador.")
                    return redirect("sales:document_list")
                except ValueError as exc:
                    messages.error(request, str(exc))
    else:
        header_form = SalesDocumentHeaderForm(
            company_id=company_id, store_id=store_id, document_type=document_type,
            initial={"document_type": document_type, "store": store_id},
        )
        line_formset = SalesDocumentLineFormSet(prefix="lines")

    return render(
        request,
        "sales/document_form.html",
        _document_form_context(company_id, header_form, line_formset, "Nuevo documento de venta"),
    )


def document_edit(request, pk):
    redirect_resp = _require_document_permission(request, "manage")
    if redirect_resp:
        return redirect_resp

    company_id, store_id = _get_ids(request)
    document = get_object_or_404(
        SalesDocument.objects.prefetch_related("lines__product__unit"),
        pk=pk,
        store_id=store_id,
    )
    if document.status != "DRAFT":
        messages.error(request, "Solo se pueden editar documentos en Borrador.")
        return redirect("sales:document_detail", pk=pk)

    if request.method == "POST":
        document_type = request.POST.get("document_type", document.document_type_id)
        header_form = SalesDocumentHeaderForm(
            request.POST,
            instance=document,
            company_id=company_id,
            store_id=store_id,
            document_type=document_type,
        )
        line_formset = SalesDocumentLineFormSet(request.POST, prefix="lines")
        if header_form.is_valid() and line_formset.is_valid():
            lines = _lines_from_formset(line_formset)
            if not lines:
                messages.error(request, "El documento debe tener al menos una línea.")
            else:
                cd = header_form.cleaned_data
                try:
                    update_sales_document_draft(
                        pk,
                        customer=cd["customer"],
                        series=cd["series"],
                        lines=lines,
                        updated_by=request.user,
                        store_id=str(cd["store"].pk),
                        document_type=cd["document_type"],
                        **_document_service_fields(cd),
                    )
                    messages.success(request, "Documento actualizado.")
                    return redirect("sales:document_detail", pk=pk)
                except ValueError as exc:
                    messages.error(request, str(exc))
    else:
        header_form = SalesDocumentHeaderForm(
            instance=document,
            company_id=company_id,
            store_id=store_id,
            document_type=document.document_type_id,
        )
        initial_lines = [
            {
                "product": str(line.product_id),
                "product_name": line.product.name,
                "unit": str(line.unit_id or line.product.unit_id),
                "product_unit": line.unit_code,
                "product_unit_id": str(line.unit_id or line.product.unit_id),
                "base_unit_id": str(line.product.unit_id),
                "base_unit_code": line.product.unit.code,
                "product_units": line.product.unit_conversions.filter(active=True).select_related("unit"),
                "description": line.description,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "price_with_igv": round(
                    float(line.unit_price) * (1 + float(line.igv_rate) / 100), 2
                ),
                "discount_amount": line.discount_amount,
                "tax_type": line.tax_type,
                "igv_rate": line.igv_rate,
                "memo": line.memo,
            }
            for line in document.lines.all()
        ]
        line_formset = SalesDocumentLineFormSet(initial=initial_lines, prefix="lines")

    return render(
        request,
        "sales/document_form.html",
        _document_form_context(
            company_id, header_form, line_formset, "Editar documento de venta", document
        ),
    )


def document_from_order(request, pk):
    """Crea un borrador de venta a partir de una orden confirmada."""
    redirect_resp = _require_document_permission(request, "manage")
    if redirect_resp:
        return redirect_resp

    if request.method != "POST":
        return redirect("sales:order_detail", pk=pk)

    company_id, store_id = _get_ids(request)
    order = get_object_or_404(SaleOrder, pk=pk, store_id=store_id)

    series_id = request.POST.get("series_id")
    document_type = request.POST.get("document_type", "01")

    if not series_id:
        messages.error(request, "Debe seleccionar una serie.")
        return redirect("sales:order_detail", pk=pk)

    try:
        series = DocumentSeries.objects.get(
            pk=series_id,
            company_id=company_id,
            store_id=store_id,
            document_type__code=document_type,
            active=True,
        )
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
            document_type=series.document_type,
            series=series,
            lines=lines,
            sale_order=order,
            created_by=request.user,
            issue_date=timezone.now().date(),
            currency=order.currency,
            notes=order.notes,
        )
        messages.success(request, "Documento de venta creado como borrador.")
        return redirect("sales:document_detail", pk=sales_document.pk)
    except (DocumentSeries.DoesNotExist, ValueError) as exc:
        messages.error(request, str(exc))
        return redirect("sales:order_detail", pk=pk)


def document_from_quotation(request, pk):
    """Crea un único borrador de venta desde una cotización aprobada."""
    redirect_resp = _require_document_permission(request, "manage")
    if redirect_resp:
        return redirect_resp
    if request.method != "POST":
        return redirect("sales:quotation_detail", pk=pk)

    company_id, store_id = _get_ids(request)
    quotation = get_object_or_404(SalesQuotation, pk=pk, store_id=store_id)
    series = get_object_or_404(
        DocumentSeries,
        pk=request.POST.get("series_id"),
        company_id=company_id,
        store_id=store_id,
        document_type__code__in=("NV", "01", "03"),
        active=True,
    )
    document_type = series.document_type
    register_inventory = request.POST.get("register_inventory_movement") == "on"
    warehouse = None
    if register_inventory:
        warehouse = get_object_or_404(
            Warehouse,
            pk=request.POST.get("warehouse_id"),
            store_id=store_id,
            active=True,
        )
    try:
        document = create_document_from_quotation(
            quotation.pk,
            document_type=document_type,
            series=series,
            created_by=request.user,
            register_inventory_movement=register_inventory,
            warehouse=warehouse,
        )
        messages.success(request, "Cotización convertida en documento de venta.")
        return redirect("sales:document_detail", pk=document.pk)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("sales:quotation_detail", pk=pk)


def document_detail(request, pk):
    redirect_resp = _require_document_permission(request, "read")
    if redirect_resp:
        return redirect_resp

    company_id, store_id = _get_ids(request)
    try:
        sales_document = get_document_detail(pk, store_id=store_id)
    except SalesDocument.DoesNotExist:
        raise Http404
    # Pass available series for credit note quick-form
    cn_series = get_series_for_store(company_id, store_id, document_type="07") if company_id and store_id else []

    return render(request, "sales/document_detail.html", {
        "sales_document": sales_document,
        "cn_series": cn_series,
        "audit_logs": AuditLog.objects.filter(
            entity="SalesDocument", entity_id=str(sales_document.pk)
        ).select_related("user")[:50],
        **_document_permissions_context(request),
    })


@require_GET
def document_preview(request, pk):
    redirect_resp = _require_document_permission(request, "read")
    if redirect_resp:
        return redirect_resp
    _, store_id = _get_ids(request)
    try:
        sales_document = get_document_detail(pk, store_id=store_id)
    except SalesDocument.DoesNotExist:
        raise Http404
    return render(
        request,
        "sales/partials/document_preview_content.html",
        {"sales_document": sales_document},
    )


@require_POST
def document_copy(request, pk):
    redirect_resp = _require_document_permission(request, "manage")
    if redirect_resp:
        return redirect_resp
    _, store_id = _get_ids(request)
    get_object_or_404(SalesDocument, pk=pk, store_id=store_id)
    try:
        copied = copy_sales_document(pk, copied_by=request.user)
        messages.success(request, "Documento copiado como borrador.")
        return redirect("sales:document_edit", pk=copied.pk)
    except (SalesDocument.DoesNotExist, ValueError) as exc:
        messages.error(request, str(exc))
        return redirect("sales:document_list")


@require_POST
def document_delete(request, pk):
    redirect_resp = _require_document_permission(request, "manage")
    if redirect_resp:
        return redirect_resp
    _, store_id = _get_ids(request)
    get_object_or_404(SalesDocument, pk=pk, store_id=store_id)
    try:
        delete_sales_document_draft(pk, deleted_by=request.user)
        messages.success(request, "Documento borrador eliminado.")
    except (SalesDocument.DoesNotExist, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("sales:document_list")


def document_issue(request, pk):
    redirect_resp = _require_document_permission(request, "authorize")
    if redirect_resp:
        return redirect_resp
    if request.method != "POST":
        return redirect("sales:document_detail", pk=pk)
    _, store_id = _get_ids(request)
    get_object_or_404(SalesDocument, pk=pk, store_id=store_id)
    try:
        v = issue_sales_document(pk, issued_by=request.user)
        messages.success(request, f"Documento {v.series_code}-{v.number} emitido.")
    except (SalesDocument.DoesNotExist, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("sales:document_detail", pk=pk)


def document_void(request, pk):
    redirect_resp = _require_document_permission(request, "authorize")
    if redirect_resp:
        return redirect_resp
    if request.method != "POST":
        return redirect("sales:document_detail", pk=pk)
    _, store_id = _get_ids(request)
    get_object_or_404(SalesDocument, pk=pk, store_id=store_id)
    reason = request.POST.get("reason", "")
    try:
        void_sales_document(pk, reason=reason, voided_by=request.user)
        messages.success(request, "Documento de venta anulado.")
    except (SalesDocument.DoesNotExist, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("sales:document_detail", pk=pk)


def document_cancel(request, pk):
    redirect_resp = _require_document_permission(request, "manage")
    if redirect_resp:
        return redirect_resp
    if request.method != "POST":
        return redirect("sales:document_detail", pk=pk)
    _, store_id = _get_ids(request)
    get_object_or_404(SalesDocument, pk=pk, store_id=store_id)
    try:
        cancel_sales_document(pk, cancelled_by=request.user)
        messages.success(request, "Documento de venta cancelado.")
    except (SalesDocument.DoesNotExist, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("sales:document_detail", pk=pk)


def document_credit(request, pk):
    """Genera una nota de crédito a partir de un comprobante ISSUED."""
    redirect_resp = _require_document_permission(request, "authorize")
    if redirect_resp:
        return redirect_resp

    company_id, store_id = _get_ids(request)
    sales_document = get_object_or_404(SalesDocument, pk=pk, store_id=store_id)

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
    redirect_resp = _require_document_permission(request, "read")
    if redirect_resp:
        return redirect_resp
    _, store_id = _get_ids(request)
    try:
        sales_document = get_document_detail(pk, store_id=store_id)
    except SalesDocument.DoesNotExist:
        raise Http404
    company = sales_document.store.company if sales_document.store else None
    return render(request, "sales/pdf/document_pdf.html", {"sales_document": sales_document, "company": company})
