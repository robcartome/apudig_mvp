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
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import format_html
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
from apps.inventory.models import PriceList, Product, Warehouse
from apps.partners.models import DocumentType
from apps.core.models import AuditLog
from apps.core.list_filters import read_list_filters, sort_queryset
from apps.companies.models import CompanyOperationalSettings
from apps.users.permissions import user_has_company_permission


SALES_DOCUMENT_SORTS = {
    "created": "created_at",
    "issue_date": ("issue_date", "created_at"),
    "series": ("series_code", "number"),
    "number": ("number", "series_code"),
    "customer": "customer_legal_name",
    "total": "total",
    "status": "status",
}

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
    company_id, store_id = _get_ids(request)
    if not user_has_company_permission(
        request.user, company_id, f"{action}.sales.documents", store_id
    ):
        return HttpResponseForbidden(
            "No tienes permiso para realizar esta acción sobre documentos de venta."
        )
    return None


def _document_permissions_context(request):
    company_id, store_id = _get_ids(request)
    return {
        "can_manage_sales_documents": user_has_company_permission(
            request.user, company_id, "manage.sales.documents", store_id
        ),
        "can_authorize_sales_documents": user_has_company_permission(
            request.user, company_id, "authorize.sales.documents", store_id
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
    operational_settings = CompanyOperationalSettings.objects.filter(company_id=company_id).first()
    settings = operational_settings or CompanyOperationalSettings(company_id=company_id)
    _restore_posted_line_metadata(line_formset, company_id)
    for form in line_formset.forms:
        form.fields["igv_rate"].initial = settings.default_igv_rate
    return {
        "header_form": header_form,
        "line_formset": line_formset,
        "title": title,
        "sales_document": document,
        "igv_rate": settings.default_igv_rate,
        "price_decimal_places": settings.price_decimal_places,
        "price_lists": PriceList.objects.filter(
            company_id=company_id, active=True
        ).order_by("name") if company_id else PriceList.objects.none(),
        "operational_settings": settings,
    }


def _restore_posted_line_metadata(line_formset, company_id):
    """Restore display-only product data after an invalid document POST."""
    if not line_formset.is_bound:
        return

    product_ids = {
        str(form["product"].value())
        for form in line_formset.forms
        if form["product"].value()
    }
    products = {
        str(product.pk): product
        for product in Product.objects.filter(
            Q(company_id=company_id) | Q(company__isnull=True),
            pk__in=product_ids,
        )
        .select_related("unit")
        .prefetch_related("unit_conversions__unit")
    }
    for form in line_formset.forms:
        product = products.get(str(form["product"].value()))
        if not product:
            continue

        unit_id = str(form["unit"].value() or product.unit_id)
        unit_code = product.unit.code
        for conversion in product.unit_conversions.all():
            if str(conversion.unit_id) == unit_id:
                unit_code = conversion.unit.code
                break

        form.initial.update({
            "product": str(product.pk),
            "product_name": product.name,
            "product_unit_id": unit_id,
            "product_unit": unit_code,
            "base_unit_id": str(product.unit_id),
            "base_unit_code": product.unit.code,
            "product_units": product.unit_conversions.all(),
        })

        try:
            unit_price = Decimal(str(form["unit_price"].value() or "0"))
            tax_type = str(form["tax_type"].value() or "10")
            igv_rate = Decimal(str(form["igv_rate"].value() or "0"))
            multiplier = (
                Decimal("1") + igv_rate / Decimal("100")
                if tax_type == "10"
                else Decimal("1")
            )
            form.initial["price_with_igv"] = unit_price * multiplier
        except (ArithmeticError, ValueError):
            pass


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
        "global_discount_amount": cleaned_data.get("global_discount_amount") or Decimal("0"),
        "global_discount_before_tax": cleaned_data.get("global_discount_before_tax", False),
        "notes": cleaned_data.get("notes", ""),
        "internal_reference": cleaned_data.get("internal_reference", ""),
        "number": cleaned_data.get("number") if cleaned_data.get("manual_number") else None,
    }


def _document_reference(document, *, link=True):
    """Safe document identifier for interactive flash messages."""
    series = document.series_code or getattr(document.series, "series", "")
    identifier = f"{series}-{document.number}" if document.number else f"{series} (correlativo pendiente)"
    if not link:
        return format_html("<strong>{}</strong>", identifier)
    return format_html(
        '<a href="{}"><strong>{}</strong></a>',
        reverse("sales:document_detail", args=[document.pk]),
        identifier,
    )


# ── Vistas ────────────────────────────────────────────────────────────────────

def document_list(request):
    redirect_resp = _require_document_permission(request, "read")
    if redirect_resp:
        return redirect_resp

    _, store_id = _get_ids(request)
    filters = read_list_filters(request)
    q = filters["q"]
    status = filters["status"]
    document_type = request.GET.get("document_type", "")
    date_from_text = filters["date_from"]
    date_to_text = filters["date_to"]
    created_from_text = filters["created_from"]
    created_to_text = filters["created_to"]
    number = filters["number"]
    series = filters["series"]
    customer = filters["party"]
    total_min_text = filters["total_min"]
    total_max_text = filters["total_max"]

    qs = search_sales_documents(
        store_id,
        query=q or None,
        status=status or None,
        date_from=filters["date_from_value"],
        date_to=filters["date_to_value"],
        created_from=filters["created_from_value"],
        created_to=filters["created_to_value"],
        number=number or None,
        series=series or None,
        customer=customer or None,
        total_min=filters["total_min_value"],
        total_max=filters["total_max_value"],
    )
    if document_type:
        qs = qs.filter(document_type__code=document_type)
    qs, table_sort = sort_queryset(
        request, qs, SALES_DOCUMENT_SORTS, default=("issue_date", "desc")
    )

    filtered_totals = list(
        SalesDocument.objects.filter(pk__in=qs.order_by().values("pk"))
        .exclude(status__in=("VOIDED", "CANCELLED", "SUNAT_REJECTED"))
        .values("currency")
        .annotate(amount=Sum("total"))
        .order_by("currency")
    )
    paginator = Paginator(qs, 80)
    page = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)

    context = {
        "page_obj": page,
        "table_sort": table_sort,
        "q": q,
        "status": status,
        "document_type": document_type,
        "date_from": date_from_text,
        "date_to": date_to_text,
        "created_from": created_from_text,
        "created_to": created_to_text,
        "number": number,
        "series": series,
        "customer": customer,
        "total_min": total_min_text,
        "total_max": total_max_text,
        "filtered_totals": filtered_totals,
        "pagination_query": query_params.urlencode(),
        "advanced_filters_active": any((
            created_from_text, created_to_text, number, series, customer,
            total_min_text, total_max_text, status, document_type,
        )),
        "list_filters": {
            **filters,
            "party": customer,
            "advanced_filters_active": any((
                created_from_text, created_to_text, number, series, customer,
                total_min_text, total_max_text, status, document_type,
            )),
        },
        "filter_search_placeholder": "Cliente, documento, serie o número",
        "filter_date_label": "Fechas de emisión",
        "filter_collapse_id": "salesAdvancedFilters",
        "filter_advanced_template": "sales/partials/document_list_filters.html",
        "filter_reset_url": reverse("sales:document_list"),
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
    company_settings = CompanyOperationalSettings.objects.filter(company_id=company_id).first()
    configured_document_type = (
        str(company_settings.default_sales_document_type_id)
        if company_settings and company_settings.default_sales_document_type_id else "NV"
    )
    document_type = request.GET.get("document_type", configured_document_type)

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
                    messages.success(request, format_html("Documento creado como borrador: {}.", _document_reference(sales_document)))
                    return redirect("sales:document_list")
                except ValueError as exc:
                    messages.error(request, str(exc))
    else:
        initial = {"document_type": document_type, "store": store_id}
        if company_settings:
            initial.update(
                customer=company_settings.default_customer_id,
                payment_method=company_settings.default_sales_payment_method_id,
            )
        header_form = SalesDocumentHeaderForm(
            company_id=company_id, store_id=store_id, document_type=document_type,
            initial=initial,
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
                    messages.success(request, format_html("Documento actualizado: {}.", _document_reference(document)))
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
                "price_with_igv": line.price_unit,
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
            issue_date=timezone.now(),
            currency=order.currency,
            notes=order.notes,
        )
        messages.success(request, format_html("Documento creado como borrador: {}.", _document_reference(sales_document)))
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
        messages.success(request, format_html("Cotización convertida en documento de venta: {}.", _document_reference(document)))
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
        messages.success(request, format_html("Documento copiado como borrador: {}.", _document_reference(copied)))
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
    document = get_object_or_404(SalesDocument, pk=pk, store_id=store_id)
    try:
        delete_sales_document_draft(pk, deleted_by=request.user)
        messages.success(request, format_html("Documento borrador eliminado: {}.", _document_reference(document, link=False)))
    except (SalesDocument.DoesNotExist, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("sales:document_list")


def document_issue(request, pk):
    redirect_resp = _require_document_permission(request, "authorize")
    if redirect_resp:
        return redirect_resp
    if request.method != "POST":
        return redirect("sales:document_list")
    _, store_id = _get_ids(request)
    get_object_or_404(SalesDocument, pk=pk, store_id=store_id)
    try:
        v = issue_sales_document(pk, issued_by=request.user)
        messages.success(request, format_html("Documento emitido: {}.", _document_reference(v)))
    except (SalesDocument.DoesNotExist, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("sales:document_list")


def document_void(request, pk):
    redirect_resp = _require_document_permission(request, "authorize")
    if redirect_resp:
        return redirect_resp
    if request.method != "POST":
        return redirect("sales:document_detail", pk=pk)
    _, store_id = _get_ids(request)
    document = get_object_or_404(SalesDocument, pk=pk, store_id=store_id)
    reason = request.POST.get("reason", "")
    try:
        void_sales_document(pk, reason=reason, voided_by=request.user)
        messages.success(request, format_html("Documento de venta anulado: {}.", _document_reference(document)))
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
    document = get_object_or_404(SalesDocument, pk=pk, store_id=store_id)
    try:
        cancel_sales_document(pk, cancelled_by=request.user)
        messages.success(request, format_html("Documento de venta cancelado: {}.", _document_reference(document)))
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
                messages.success(request, format_html("Nota de crédito creada: {}.", _document_reference(note)))
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
