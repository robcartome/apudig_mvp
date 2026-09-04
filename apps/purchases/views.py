from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.companies.models import CompanyOperationalSettings, Store
from apps.core.models import AuditLog
from apps.inventory.models import Category, Movement, MovementStatus, MovementType, Product, Unit
from apps.partners.models import Supplier
from apps.sales.models import MeansOfPayment
from apps.users.permissions import user_has_company_permission

from .forms import (
    PurchaseCategoryForm, PurchaseDocumentForm, PurchaseDocumentReceiptLinkForm, PurchaseDocumentLineFormSet, PurchaseExpenseLineFormSet,
    PurchaseOrderForm, PurchaseOrderLineFormSet, PurchaseReceiptForm, PurchaseReceiptLineFormSet,
    SupplierPaymentForm,
    PurchaseInstallmentFormSet,
    PurchaseLandedCostAllocationFormSet, PurchaseLandedCostForm,
)
from .models import (
    PurchaseCategory, PurchaseDocument, PurchaseDocumentLine, PurchaseDocumentStatus,
    PurchaseOrder, PurchaseOrderStatus, PurchaseReceipt, SupplierPayment,
    PurchaseLandedCost,
)
from .order_services import (
    approve_purchase_order, cancel_purchase_order, create_purchase_order, update_purchase_order,
)
from .receipt_services import cancel_purchase_receipt, received_quantities, register_purchase_receipt
from .payment_services import (
    cancel_supplier_payment, document_payment_summary, installment_paid_amount,
    register_supplier_payment, replace_installment_schedule,
)
from .landed_cost_services import (
    allocate_landed_cost, cancel_landed_cost, document_landed_cost_summary,
)
from .selectors import (
    get_purchase_analytics, get_purchase_document, get_purchase_price_history,
    search_purchase_documents,
)
from .services import (
    cancel_purchase_document,
    create_purchase_document_draft,
    delete_purchase_document_draft,
    register_purchase_document,
    reconcile_purchase_document_receipts,
    update_purchase_document_draft,
)


def _ids(request):
    company_id = getattr(request, "active_company_id", None) or request.session.get("active_company_id")
    store_id = getattr(request, "active_store_id", None) or request.session.get("active_store_id")
    return company_id, store_id


def _require_permission(request, action):
    if not request.user.is_authenticated:
        return redirect("login")
    company_id, _ = _ids(request)
    if not user_has_company_permission(request.user, company_id, f"{action}.purchases.documents"):
        return HttpResponseForbidden("No tienes permiso para realizar esta accion sobre compras.")
    return None


def _require_category_settings_permission(request):
    if request.user.is_authenticated and request.user.is_staff:
        return None
    return _require_permission(request, "manage")


def _permission_context(request):
    company_id, _ = _ids(request)
    return {
        "can_manage_purchase_documents": user_has_company_permission(
            request.user, company_id, "manage.purchases.documents"
        ),
        "can_authorize_purchase_documents": user_has_company_permission(
            request.user, company_id, "authorize.purchases.documents"
        ),
    }


def _active_scope(request):
    company_id, store_id = _ids(request)
    if not company_id or not store_id:
        raise Http404("Debe seleccionar una empresa y sucursal.")
    try:
        store = Store.objects.get(pk=store_id, company_id=company_id, active=True)
    except (Store.DoesNotExist, ValueError):
        raise Http404("La sucursal activa no es valida.")
    return company_id, store


def _document_or_404(request, pk):
    company_id, store = _active_scope(request)
    try:
        return get_purchase_document(company_id, store.pk, pk)
    except (ObjectDoesNotExist, ValueError):
        raise Http404


def _lines(formset):
    return [
        form.cleaned_data for form in formset
        if form.cleaned_data
        and not form.cleaned_data.get("DELETE")
        and (form.cleaned_data.get("product") or form.cleaned_data.get("purchase_category"))
    ]


def _initial_lines(document):
    return [
        {
            "product": line.product_id,
            "product_name": (
                f"{line.product.sku} | {line.product.name}"
                if line.product_id and line.product.sku
                else (line.product.name if line.product_id else "")
            ),
            "purchase_category": line.purchase_category_id,
            "description": line.description,
            "unit": line.unit_id,
            "quantity": line.quantity,
            "unit_price": line.unit_price,
            "discount_amount": line.discount_amount,
            "tax_type": line.tax_type,
            "igv_rate": line.igv_rate,
            "update_purchase_price": line.update_purchase_price,
            "memo": line.memo,
        }
        for line in document.lines.all()
    ]


def _prepare_line_forms(formset, company_id):
    for line_form in formset.forms:
        product_id = (
            line_form.data.get(line_form.add_prefix("product"))
            if line_form.is_bound else line_form.initial.get("product")
        )
        if not product_id:
            continue
        product = Product.objects.filter(pk=product_id, company_id=company_id).select_related("unit").prefetch_related("unit_conversions__unit").first()
        if not product:
            continue
        conversions = list(product.unit_conversions.filter(active=True))
        if not any(str(conversion.unit_id) == str(product.unit_id) for conversion in conversions):
            conversions.insert(0, {
                "unit_id": product.unit_id,
                "unit": product.unit,
                "conversion_factor": 1,
                "purchase_price": None,
            })
        line_form.initial.update({
            "product_name": (
                f"{product.sku} | {product.name}" if product.sku else product.name
            ),
            "product_unit_id": line_form.data.get(line_form.add_prefix("unit")) if line_form.is_bound else line_form.initial.get("unit") or product.unit_id,
            "product_unit": product.unit.code,
            "base_unit_id": product.unit_id,
            "base_unit_code": product.unit.code,
            "product_units": conversions,
        })


def _form_context(form, formset, company_id, title, document=None):
    _prepare_line_forms(formset, company_id)
    supplier_id = form["supplier"].value()
    selected_supplier = Supplier.objects.filter(pk=supplier_id, company_id=company_id).first() if supplier_id else None
    operational_settings = CompanyOperationalSettings.objects.filter(company_id=company_id).first()
    return {
        "form": form,
        "formset": formset,
        "title": title,
        "purchase_document": document,
        "selected_supplier": selected_supplier,
        "units": Unit.objects.all().order_by("code"),
        "product_categories": Category.objects.filter(
            company_id=company_id, active=True
        ).order_by("name"),
        "operational_settings": operational_settings or CompanyOperationalSettings(company_id=company_id),
        "payment_methods": list(form.fields["payment_method"].queryset.values("id", "is_cash")),
        "price_decimal_places": operational_settings.price_decimal_places if operational_settings else 2,
        "default_igv_rate": operational_settings.default_igv_rate if operational_settings else 18,
    }


def purchase_document_list(request):
    denied = _require_permission(request, "read")
    if denied:
        return denied
    company_id, store = _active_scope(request)
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    qs = search_purchase_documents(company_id, store.pk, query or None, status or None)
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "purchases/document_list.html", {
        "page_obj": page,
        "q": query,
        "status": status,
        "status_choices": PurchaseDocumentStatus.choices,
        "payment_means": MeansOfPayment.objects.filter(
            company_id=company_id, active=True
        ).order_by("name"),
        "quick_payment_number": f"PAG-{SupplierPayment.objects.filter(company_id=company_id).count() + 1:06d}",
        "quick_payment_date": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
        **_permission_context(request),
    })


@require_GET
def purchase_receipt_movements_api(request):
    """Ingresos confirmados disponibles para poblar una factura del proveedor."""
    denied = _require_permission(request, "read")
    if denied:
        return denied
    company_id, store = _active_scope(request)
    supplier_id = request.GET.get("supplier")
    if not supplier_id:
        return JsonResponse({"movements": []})
    linked_movement_ids = []
    document_id = request.GET.get("document")
    if document_id:
        linked_movement_ids = PurchaseDocumentLine.objects.filter(
            purchase_document_id=document_id,
            purchase_document__company_id=company_id,
            purchase_document__store_id=store.pk,
            receipt_matches__isnull=False,
        ).values_list("receipt_matches__movement_detail__movement_id", flat=True)
    movements = (
        Movement.objects.filter(
            store_id=store.pk, supplier_id=supplier_id,
            type=MovementType.ENTRY, status=MovementStatus.CONFIRMED,
            purchase_document__isnull=True,
        )
        .filter(Q(details__purchase_receipt_matches__isnull=True) | Q(pk__in=linked_movement_ids))
        .prefetch_related("details__product__unit_conversions__unit", "details__unit")
        .order_by("-date")
        .distinct()
    )
    payload = []
    for movement in movements:
        details = []
        for detail in movement.details.all():
            product = detail.product
            conversions = list(product.unit_conversions.filter(active=True))
            if not any(conversion.unit_id == product.unit_id for conversion in conversions):
                conversions.insert(0, None)
            units = [
                {
                    "id": str(product.unit_id if conversion is None else conversion.unit_id),
                    "code": product.unit.code if conversion is None else conversion.unit.code,
                    "name": product.unit.name if conversion is None else conversion.unit.name,
                    "factor": 1 if conversion is None else str(conversion.conversion_factor),
                    "purchase_price": None if conversion is None else str(conversion.purchase_price or ""),
                }
                for conversion in conversions
            ]
            details.append({
                "id": str(detail.pk),
                "product": {
                    "id": str(product.pk), "name": product.name, "sku": product.sku,
                    "barcode": product.barcode,
                    "unit_id": str(product.unit_id), "unit": product.unit.code,
                    "price_purchase": str(product.price_purchase), "units": units,
                },
                "quantity": str(detail.quantity), "unit_id": str(detail.unit_id),
                "unit_price": str(detail.unit_price),
            })
        payload.append({
            "id": str(movement.pk), "number": movement.number or "Sin número",
            "reference": movement.reference_doc, "date": movement.date.strftime("%d/%m/%Y %H:%M"),
            "warehouse": str(movement.warehouse), "warehouse_id": str(movement.warehouse_id or ""),
            "details": details,
        })
    return JsonResponse({"movements": payload})


def purchase_category_create(request):
    denied = _require_category_settings_permission(request)
    if denied:
        return denied
    company_id, _ = _active_scope(request)
    form = PurchaseCategoryForm(request.POST or None, company_id=company_id)
    if request.method == "POST" and form.is_valid():
        category = form.save(commit=False)
        category.company_id = company_id
        category.save()
        messages.success(request, "Categoria de gasto creada.")
        return redirect(f"{reverse('users:configuracion')}?item=categorias_gasto")
    return render(request, "purchases/expense_category_form.html", {"form": form, "title": "Nueva categoria de gasto"})


def purchase_category_update(request, pk):
    denied = _require_category_settings_permission(request)
    if denied:
        return denied
    company_id, _ = _active_scope(request)
    category = PurchaseCategory.objects.filter(pk=pk, company_id=company_id).first()
    if not category:
        raise Http404
    form = PurchaseCategoryForm(request.POST or None, instance=category, company_id=company_id)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Categoria de gasto actualizada.")
        return redirect(f"{reverse('users:configuracion')}?item=categorias_gasto")
    return render(request, "purchases/expense_category_form.html", {"form": form, "title": "Editar categoria de gasto"})


@require_POST
def purchase_category_toggle(request, pk):
    denied = _require_category_settings_permission(request)
    if denied:
        return denied
    company_id, _ = _active_scope(request)
    category = PurchaseCategory.objects.filter(pk=pk, company_id=company_id).first()
    if not category:
        raise Http404
    category.active = not category.active
    category.save(update_fields=("active", "updated_at"))
    messages.success(request, f"Categoria {'activada' if category.active else 'desactivada'}.")
    return redirect(f"{reverse('users:configuracion')}?item=categorias_gasto")


def purchase_category_delete(request, pk):
    denied = _require_category_settings_permission(request)
    if denied:
        return denied
    company_id, _ = _active_scope(request)
    category = PurchaseCategory.objects.filter(pk=pk, company_id=company_id).first()
    if not category:
        raise Http404
    if request.method == "POST":
        if category.document_lines.exists() or category.order_lines.exists():
            messages.error(request, "La categoria esta en uso; puede desactivarla, pero no eliminarla.")
        else:
            category.delete()
            messages.success(request, "Categoria de gasto eliminada.")
        return redirect(f"{reverse('users:configuracion')}?item=categorias_gasto")
    return render(request, "purchases/expense_category_confirm_delete.html", {"object": category})


def purchase_document_create(request):
    denied = _require_permission(request, "manage")
    if denied:
        return denied
    company_id, store = _active_scope(request)
    settings = CompanyOperationalSettings.objects.filter(company_id=company_id).first()
    initial = {"issue_date": timezone.localdate()}
    if settings:
        initial.update(
            supplier=settings.default_supplier_id,
            document_type=settings.default_purchase_document_type_id,
            payment_method=settings.default_purchase_payment_method_id,
        )
    form = PurchaseDocumentForm(
        request.POST or None,
        company_id=company_id,
        store_id=store.pk,
        initial=initial,
    )
    default_igv_rate = settings.default_igv_rate if settings else 18
    formset = PurchaseDocumentLineFormSet(
        request.POST or None, prefix="lines",
        form_kwargs={"company_id": company_id, "default_igv_rate": default_igv_rate},
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        try:
            document = create_purchase_document_draft(
                company_id=company_id,
                store=store,
                supplier=form.cleaned_data["supplier"],
                purchase_order=form.cleaned_data.get("purchase_order"),
                document_type=form.cleaned_data["document_type"],
                lines=_lines(formset),
                created_by=request.user,
                series=form.cleaned_data["series"],
                number=form.cleaned_data["number"],
                issue_date=form.cleaned_data["issue_date"],
                due_date=form.cleaned_data.get("due_date"),
                payment_method=form.cleaned_data.get("payment_method"),
                currency=form.cleaned_data["currency"],
                exchange_rate=form.cleaned_data["exchange_rate"],
                register_inventory_movement=form.cleaned_data.get("register_inventory_movement", False),
                receipt_movements=form.cleaned_data.get("receipt_movements"),
                warehouse=form.cleaned_data.get("warehouse"),
                notes=form.cleaned_data.get("notes", ""),
                internal_reference=form.cleaned_data.get("internal_reference", ""),
            )
        except IntegrityError:
            form.add_error(None, "Ya existe un documento con el mismo proveedor, tipo, serie y numero.")
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Documento de compra creado correctamente.")
            return redirect("purchases:document_list")
    return render(request, "purchases/document_form.html", _form_context(
        form, formset, company_id, "Nuevo documento de compra"
    ))


def _expense_initial_lines(document):
    return [{
        "purchase_category": line.purchase_category_id,
        "description": line.description,
        "quantity": line.quantity,
        "unit_price": line.unit_price,
        "discount_amount": line.discount_amount,
        "tax_type": line.tax_type,
        "igv_rate": line.igv_rate,
        "memo": line.memo,
    } for line in document.lines.all()]


def _expense_context(form, formset, company_id, title, document=None):
    supplier_id = form["supplier"].value()
    return {
        "form": form,
        "formset": formset,
        "title": title,
        "purchase_document": document,
        "selected_supplier": Supplier.objects.filter(
            pk=supplier_id, company_id=company_id
        ).first() if supplier_id else None,
    }


def purchase_expense_create(request):
    denied = _require_permission(request, "manage")
    if denied:
        return denied
    company_id, store = _active_scope(request)
    settings = CompanyOperationalSettings.objects.filter(company_id=company_id).first()
    initial = {"issue_date": timezone.localdate()}
    if settings:
        initial.update(
            supplier=settings.default_supplier_id,
            document_type=settings.default_purchase_document_type_id,
            payment_method=settings.default_purchase_payment_method_id,
        )
    form = PurchaseDocumentForm(
        request.POST or None, company_id=company_id, store_id=store.pk,
        initial=initial,
    )
    default_igv_rate = settings.default_igv_rate if settings else 18
    formset = PurchaseExpenseLineFormSet(
        request.POST or None, prefix="lines",
        form_kwargs={"company_id": company_id, "default_igv_rate": default_igv_rate},
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        try:
            document = create_purchase_document_draft(
                company_id=company_id, store=store,
                supplier=form.cleaned_data["supplier"], document_type=form.cleaned_data["document_type"],
                lines=_lines(formset), created_by=request.user,
                series=form.cleaned_data["series"], number=form.cleaned_data["number"],
                issue_date=form.cleaned_data["issue_date"], due_date=form.cleaned_data.get("due_date"),
                payment_method=form.cleaned_data.get("payment_method"),
                currency=form.cleaned_data["currency"], exchange_rate=form.cleaned_data["exchange_rate"],
                purchase_order=None, register_inventory_movement=False, warehouse=None,
                notes=form.cleaned_data.get("notes", ""),
                internal_reference=form.cleaned_data.get("internal_reference", ""),
            )
        except (ValidationError, ValueError) as exc:
            form.add_error(None, "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
        except IntegrityError:
            form.add_error(None, "Ya existe un documento con el mismo proveedor, tipo, serie y numero.")
        else:
            messages.success(request, "Gasto creado correctamente.")
            return redirect("purchases:document_detail", pk=document.pk)
    return render(request, "purchases/expense_form.html", _expense_context(
        form, formset, company_id, "Nuevo gasto o servicio"
    ))


def purchase_expense_edit(request, pk):
    denied = _require_permission(request, "manage")
    if denied:
        return denied
    company_id, store = _active_scope(request)
    document = _document_or_404(request, pk)
    if document.document_status != PurchaseDocumentStatus.DRAFT or not document.is_expense:
        raise Http404
    form = PurchaseDocumentForm(
        request.POST or None, instance=document, company_id=company_id, store_id=store.pk
    )
    formset = PurchaseExpenseLineFormSet(
        request.POST or None, prefix="lines", form_kwargs={"company_id": company_id},
        initial=None if request.method == "POST" else _expense_initial_lines(document),
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        try:
            document = update_purchase_document_draft(
                document.pk, company_id=company_id, store=store,
                supplier=form.cleaned_data["supplier"], document_type=form.cleaned_data["document_type"],
                lines=_lines(formset), updated_by=request.user,
                series=form.cleaned_data["series"], number=form.cleaned_data["number"],
                issue_date=form.cleaned_data["issue_date"], due_date=form.cleaned_data.get("due_date"),
                payment_method=form.cleaned_data.get("payment_method"),
                currency=form.cleaned_data["currency"], exchange_rate=form.cleaned_data["exchange_rate"],
                purchase_order=None, register_inventory_movement=False, warehouse=None,
                notes=form.cleaned_data.get("notes", ""),
                internal_reference=form.cleaned_data.get("internal_reference", ""),
            )
        except (ValidationError, ValueError) as exc:
            form.add_error(None, "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
        except IntegrityError:
            form.add_error(None, "Ya existe un documento con el mismo proveedor, tipo, serie y numero.")
        else:
            messages.success(request, "Gasto actualizado correctamente.")
            return redirect("purchases:document_detail", pk=document.pk)
    return render(request, "purchases/expense_form.html", _expense_context(
        form, formset, company_id, "Editar gasto o servicio", document
    ))


def purchase_document_edit(request, pk):
    denied = _require_permission(request, "manage")
    if denied:
        return denied
    company_id, store = _active_scope(request)
    document = _document_or_404(request, pk)
    if document.is_expense:
        return redirect("purchases:expense_edit", pk=document.pk)
    if document.document_status != PurchaseDocumentStatus.DRAFT:
        messages.error(request, "Solo se pueden editar documentos en borrador.")
        return redirect("purchases:document_detail", pk=document.pk)
    form = PurchaseDocumentForm(
        request.POST or None,
        instance=document,
        company_id=company_id,
        store_id=store.pk,
    )
    formset = PurchaseDocumentLineFormSet(
        request.POST or None,
        prefix="lines",
        initial=None if request.method == "POST" else _initial_lines(document),
        form_kwargs={
            "company_id": company_id,
            "default_igv_rate": CompanyOperationalSettings.objects.filter(
                company_id=company_id
            ).values_list("default_igv_rate", flat=True).first() or 18,
        },
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        try:
            update_purchase_document_draft(
                document.pk,
                company_id=company_id,
                store=store,
                supplier=form.cleaned_data["supplier"],
                purchase_order=form.cleaned_data.get("purchase_order"),
                document_type=form.cleaned_data["document_type"],
                lines=_lines(formset),
                updated_by=request.user,
                series=form.cleaned_data["series"],
                number=form.cleaned_data["number"],
                issue_date=form.cleaned_data["issue_date"],
                due_date=form.cleaned_data.get("due_date"),
                payment_method=form.cleaned_data.get("payment_method"),
                currency=form.cleaned_data["currency"],
                exchange_rate=form.cleaned_data["exchange_rate"],
                register_inventory_movement=form.cleaned_data.get("register_inventory_movement", False),
                receipt_movements=form.cleaned_data.get("receipt_movements"),
                warehouse=form.cleaned_data.get("warehouse"),
                notes=form.cleaned_data.get("notes", ""),
                internal_reference=form.cleaned_data.get("internal_reference", ""),
            )
        except IntegrityError:
            form.add_error(None, "Ya existe un documento con el mismo proveedor, tipo, serie y numero.")
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Documento de compra actualizado.")
            return redirect("purchases:document_detail", pk=document.pk)
    return render(request, "purchases/document_form.html", _form_context(
        form, formset, company_id, "Editar documento de compra", document
    ))


def purchase_document_detail(request, pk):
    denied = _require_permission(request, "read")
    if denied:
        return denied
    document = _document_or_404(request, pk)
    audit_logs = AuditLog.objects.filter(entity="PurchaseDocument", entity_id=str(document.pk)).select_related("user")
    payment_summary = document_payment_summary(document)
    payments = SupplierPayment.objects.filter(
        allocations__installment__purchase_document=document
    ).select_related("means_of_payment").distinct()
    landed_summary = document_landed_cost_summary(document)
    landed_rows = []
    for line in document.lines.all():
        allocated = landed_summary["by_line"].get(line.pk, 0)
        landed_rows.append({
            "line": line, "allocated": allocated,
            "acquired_unit_cost": line.unit_price + (allocated / line.quantity if line.quantity else 0),
        })
    linked_receipt_movements = (
        Movement.objects.filter(
            details__purchase_receipt_matches__purchase_document_line__purchase_document=document
        )
        .select_related("warehouse", "supplier")
        .distinct()
        .order_by("-date")
    )
    return render(request, "purchases/document_detail.html", {
        "purchase_document": document,
        "audit_logs": audit_logs,
        "payment_summary": payment_summary,
        "supplier_payments": payments,
        "landed_cost_summary": landed_summary, "landed_rows": landed_rows,
        "linked_receipt_movements": linked_receipt_movements,
        "receipt_link_form": PurchaseDocumentReceiptLinkForm(document=document),
        **_permission_context(request),
    })


@require_POST
def purchase_document_reconcile_receipts(request, pk):
    denied = _require_permission(request, "manage")
    if denied:
        return denied
    company_id, _ = _active_scope(request)
    document = _document_or_404(request, pk)
    form = PurchaseDocumentReceiptLinkForm(request.POST, document=document)
    if form.is_valid():
        try:
            reconcile_purchase_document_receipts(
                document.pk,
                company_id=company_id,
                receipt_movements=form.cleaned_data["receipt_movements"],
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Recepción conciliada con la factura.")
    else:
        messages.error(request, "Selecciona al menos un ingreso confirmado del mismo proveedor.")
    return redirect("purchases:document_detail", pk=document.pk)


@require_GET
def purchase_document_preview(request, pk):
    """Fragmento de detalle para la vista rápida del listado."""
    denied = _require_permission(request, "read")
    if denied:
        return denied
    document = _document_or_404(request, pk)
    linked_receipt_movements = Movement.objects.filter(
        details__purchase_receipt_matches__purchase_document_line__purchase_document=document
    ).select_related("warehouse").distinct().order_by("-date")
    return render(request, "purchases/partials/document_preview_content.html", {
        "purchase_document": document,
        "linked_receipt_movements": linked_receipt_movements,
    })


@require_POST
def purchase_document_register(request, pk):
    denied = _require_permission(request, "authorize")
    if denied:
        return denied
    company_id, _ = _active_scope(request)
    document = _document_or_404(request, pk)
    try:
        register_purchase_document(document.pk, company_id=company_id, registered_by=request.user)
        messages.success(request, "Documento de compra registrado correctamente.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("purchases:document_list")


@require_POST
def purchase_document_cancel(request, pk):
    denied = _require_permission(request, "authorize")
    if denied:
        return denied
    company_id, _ = _active_scope(request)
    document = _document_or_404(request, pk)
    try:
        cancel_purchase_document(document.pk, company_id=company_id, cancelled_by=request.user)
        messages.success(request, "Documento de compra cancelado.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("purchases:document_detail", pk=document.pk)


@require_POST
def purchase_document_delete(request, pk):
    denied = _require_permission(request, "manage")
    if denied:
        return denied
    company_id, _ = _active_scope(request)
    document = _document_or_404(request, pk)
    try:
        delete_purchase_document_draft(document.pk, company_id=company_id, deleted_by=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("purchases:document_detail", pk=document.pk)
    messages.success(request, "Documento de compra eliminado.")
    return redirect("purchases:document_list")


def purchase_price_history(request):
    denied = _require_permission(request, "read")
    if denied:
        return denied
    company_id, store = _active_scope(request)
    product_id = request.GET.get("product", "")
    supplier_id = request.GET.get("supplier", "")
    date_from = request.GET.get("date_from") or None
    date_to = request.GET.get("date_to") or None
    rows = get_purchase_price_history(
        company_id, store.pk,
        product_id=product_id or None,
        supplier_id=supplier_id or None,
        date_from=date_from,
        date_to=date_to,
    )
    return render(request, "purchases/price_history.html", {
        "rows": rows,
        "products": Product.objects.filter(company_id=company_id, active=True).order_by("name"),
        "suppliers": Supplier.objects.filter(company_id=company_id, active=True).order_by("name"),
        "product_id": product_id,
        "supplier_id": supplier_id,
        "date_from": date_from or "",
        "date_to": date_to or "",
    })


def purchase_analytics(request):
    denied = _require_permission(request, "read")
    if denied:
        return denied
    company_id, store = _active_scope(request)
    supplier_id = request.GET.get("supplier", "")
    date_from_raw = request.GET.get("date_from", "")
    date_to_raw = request.GET.get("date_to", "")
    date_from, date_to = parse_date(date_from_raw), parse_date(date_to_raw)
    report = get_purchase_analytics(
        company_id, store.pk, supplier_id=supplier_id or None,
        date_from=date_from, date_to=date_to,
    )
    if request.GET.get("format") == "csv":
        import csv
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="reporte_compras_proveedores.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(["Proveedor", "Documentos", "Compras PEN", "Pagado PEN", "Saldo PEN", "Costos adicionales PEN"])
        for row in report["supplier_rows"]:
            writer.writerow([
                row["supplier"].name, row["document_count"], row["spend_pen"],
                row["paid_pen"], row["balance_pen"], row["landed_cost_pen"],
            ])
        return response
    return render(request, "purchases/analytics.html", {
        "report": report,
        "suppliers": Supplier.objects.filter(company_id=company_id, active=True).order_by("name"),
        "supplier_id": supplier_id, "date_from": date_from_raw, "date_to": date_to_raw,
    })


def _order_or_404(request, pk):
    company_id, store = _active_scope(request)
    try:
        return PurchaseOrder.objects.select_related("supplier", "store").prefetch_related(
            "lines__product", "lines__purchase_category", "lines__unit"
        ).get(pk=pk, company_id=company_id, store_id=store.pk)
    except (PurchaseOrder.DoesNotExist, ValueError):
        raise Http404


def _order_initial_lines(order):
    return [{
        "product": line.product_id, "purchase_category": line.purchase_category_id,
        "description": line.description, "unit": line.unit_id,
        "quantity": line.quantity, "unit_price": line.unit_price,
        "discount_amount": line.discount_amount, "tax_type": line.tax_type,
        "igv_rate": line.igv_rate, "update_purchase_price": False, "memo": line.memo,
    } for line in order.lines.all()]


def _order_form_context(form, formset, company_id, title, order=None):
    context = _form_context(form, formset, company_id, title)
    context.update({"purchase_order": order, "is_purchase_order": True})
    return context


def purchase_order_list(request):
    denied = _require_permission(request, "read")
    if denied:
        return denied
    company_id, store = _active_scope(request)
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    orders = PurchaseOrder.objects.filter(company_id=company_id, store_id=store.pk).select_related("supplier")
    if query:
        orders = orders.filter(order_number__icontains=query) | orders.filter(supplier__name__icontains=query)
    if status:
        orders = orders.filter(status=status)
    return render(request, "purchases/order_list.html", {
        "page_obj": Paginator(orders.order_by("-order_date", "-created_at"), 25).get_page(request.GET.get("page")),
        "q": query, "status": status, "status_choices": PurchaseOrderStatus.choices,
        **_permission_context(request),
    })


def purchase_order_create(request):
    denied = _require_permission(request, "manage")
    if denied:
        return denied
    company_id, store = _active_scope(request)
    form = PurchaseOrderForm(request.POST or None, company_id=company_id, store_id=store.pk, initial={"order_date": timezone.localdate()})
    formset = PurchaseOrderLineFormSet(request.POST or None, prefix="lines", form_kwargs={"company_id": company_id})
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        try:
            order = create_purchase_order(
                company_id=company_id, store=store, supplier=form.cleaned_data["supplier"],
                lines=_lines(formset), created_by=request.user,
                order_number=form.cleaned_data["order_number"], order_date=form.cleaned_data["order_date"],
                expected_date=form.cleaned_data.get("expected_date"), currency=form.cleaned_data["currency"],
                exchange_rate=form.cleaned_data["exchange_rate"], notes=form.cleaned_data.get("notes", ""),
            )
        except IntegrityError:
            form.add_error("order_number", "Ya existe una orden con este numero.")
        except (ValidationError, ValueError) as exc:
            form.add_error(None, "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
        else:
            messages.success(request, "Orden de compra creada correctamente.")
            return redirect("purchases:order_detail", pk=order.pk)
    return render(request, "purchases/order_form.html", _order_form_context(form, formset, company_id, "Nueva orden de compra"))


def purchase_order_edit(request, pk):
    denied = _require_permission(request, "manage")
    if denied:
        return denied
    company_id, store = _active_scope(request)
    order = _order_or_404(request, pk)
    if order.status != PurchaseOrderStatus.DRAFT:
        messages.error(request, "Solo se pueden editar ordenes en borrador.")
        return redirect("purchases:order_detail", pk=order.pk)
    form = PurchaseOrderForm(request.POST or None, instance=order, company_id=company_id, store_id=store.pk)
    formset = PurchaseOrderLineFormSet(
        request.POST or None, prefix="lines",
        initial=None if request.method == "POST" else _order_initial_lines(order),
        form_kwargs={"company_id": company_id},
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        try:
            update_purchase_order(
                order.pk, company_id=company_id, store=store, supplier=form.cleaned_data["supplier"],
                lines=_lines(formset), updated_by=request.user,
                order_number=form.cleaned_data["order_number"], order_date=form.cleaned_data["order_date"],
                expected_date=form.cleaned_data.get("expected_date"), currency=form.cleaned_data["currency"],
                exchange_rate=form.cleaned_data["exchange_rate"], notes=form.cleaned_data.get("notes", ""),
            )
        except IntegrityError:
            form.add_error("order_number", "Ya existe una orden con este numero.")
        except (ValidationError, ValueError) as exc:
            form.add_error(None, "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
        else:
            messages.success(request, "Orden de compra actualizada.")
            return redirect("purchases:order_detail", pk=order.pk)
    return render(request, "purchases/order_form.html", _order_form_context(form, formset, company_id, "Editar orden de compra", order))


def purchase_order_detail(request, pk):
    denied = _require_permission(request, "read")
    if denied:
        return denied
    order = _order_or_404(request, pk)
    received = received_quantities(order)
    invoiced = {}
    for invoice_line in PurchaseDocumentLine.objects.filter(
        purchase_order_line__purchase_order=order,
        purchase_document__document_status=PurchaseDocumentStatus.REGISTERED,
    ):
        bucket = invoiced.setdefault(invoice_line.purchase_order_line_id, {"quantity": 0, "amount": 0})
        bucket["quantity"] += invoice_line.quantity
        bucket["amount"] += invoice_line.quantity * invoice_line.unit_price
    matching_rows = []
    for line in order.lines.all():
        received_qty = received.get(line.pk, 0)
        invoice_data = invoiced.get(line.pk, {"quantity": 0, "amount": 0})
        invoiced_qty = invoice_data["quantity"]
        invoiced_price = invoice_data["amount"] / invoiced_qty if invoiced_qty else None
        matching_rows.append({
            "line": line, "received": received_qty, "invoiced": invoiced_qty,
            "pending_receipt": max(line.quantity - received_qty, 0),
            "pending_invoice": max(line.quantity - invoiced_qty, 0),
            "invoiced_price": invoiced_price,
            "price_variance": invoiced_price - line.unit_price if invoiced_price is not None else None,
        })
    return render(request, "purchases/order_detail.html", {
        "purchase_order": order, "matching_rows": matching_rows,
        **_permission_context(request),
    })


@require_POST
def purchase_order_approve(request, pk):
    denied = _require_permission(request, "authorize")
    if denied:
        return denied
    company_id, _ = _active_scope(request)
    order = _order_or_404(request, pk)
    try:
        approve_purchase_order(order.pk, company_id=company_id, approved_by=request.user)
        messages.success(request, "Orden de compra aprobada.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("purchases:order_detail", pk=order.pk)


@require_POST
def purchase_order_cancel(request, pk):
    denied = _require_permission(request, "authorize")
    if denied:
        return denied
    company_id, _ = _active_scope(request)
    order = _order_or_404(request, pk)
    try:
        cancel_purchase_order(order.pk, company_id=company_id, cancelled_by=request.user)
        messages.success(request, "Orden de compra cancelada.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("purchases:order_detail", pk=order.pk)


def purchase_receipt_create(request, order_pk):
    denied = _require_permission(request, "manage")
    if denied:
        return denied
    company_id, store = _active_scope(request)
    order = _order_or_404(request, order_pk)
    received = received_quantities(order)
    receivable_lines = [
        line for line in order.lines.all()
        if line.product_id and line.product.tracks_inventory and line.quantity > received.get(line.pk, 0)
    ]
    initial_lines = [{
        "purchase_order_line": line.pk,
        "quantity": line.quantity - received.get(line.pk, 0),
    } for line in receivable_lines]
    initial_header = {
        "receipt_date": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
        "receipt_number": f"REC-{order.receipts.count() + 1:03d}",
    }
    form = PurchaseReceiptForm(request.POST or None, store_id=store.pk, initial=initial_header)
    formset = PurchaseReceiptLineFormSet(
        request.POST or None, prefix="lines", initial=None if request.method == "POST" else initial_lines,
        form_kwargs={"order": order},
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        try:
            register_purchase_receipt(
                order_id=order.pk, company_id=company_id,
                warehouse=form.cleaned_data["warehouse"], receipt_number=form.cleaned_data["receipt_number"],
                receipt_date=form.cleaned_data["receipt_date"], notes=form.cleaned_data.get("notes", ""),
                lines=[line.cleaned_data for line in formset if line.cleaned_data], created_by=request.user,
            )
        except IntegrityError:
            form.add_error("receipt_number", "Ya existe una recepcion con este numero para la orden.")
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Recepcion registrada e inventario actualizado.")
            return redirect("purchases:order_detail", pk=order.pk)
    return render(request, "purchases/receipt_form.html", {
        "form": form, "formset": formset, "purchase_order": order,
        "receivable_lines": receivable_lines,
        "receipt_rows": zip(formset.forms, receivable_lines),
    })


@require_POST
def purchase_receipt_cancel(request, pk):
    denied = _require_permission(request, "authorize")
    if denied:
        return denied
    company_id, store = _active_scope(request)
    try:
        receipt = PurchaseReceipt.objects.select_related("purchase_order").get(
            pk=pk, purchase_order__company_id=company_id, purchase_order__store_id=store.pk
        )
    except PurchaseReceipt.DoesNotExist:
        raise Http404
    try:
        cancel_purchase_receipt(receipt.pk, company_id=company_id, cancelled_by=request.user)
        messages.success(request, "Recepcion cancelada y stock revertido.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("purchases:order_detail", pk=receipt.purchase_order_id)


def supplier_payment_create(request, document_pk):
    denied = _require_permission(request, "manage")
    if denied:
        return denied
    company_id, store = _active_scope(request)
    document = _document_or_404(request, document_pk)
    if document.document_status != PurchaseDocumentStatus.REGISTERED:
        messages.error(request, "Solo se pueden pagar documentos registrados.")
        return redirect("purchases:document_detail", pk=document.pk)
    summary = document_payment_summary(document)
    if summary["balance"] <= 0:
        messages.info(request, "El documento ya se encuentra pagado.")
        return redirect("purchases:document_detail", pk=document.pk)
    initial = {
        "payment_number": f"PAG-{SupplierPayment.objects.filter(company_id=company_id).count() + 1:06d}",
        "payment_date": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
        "amount": summary["balance"],
    }
    form = SupplierPaymentForm(request.POST or None, company_id=company_id, initial=initial)
    if request.method == "POST" and form.is_valid():
        amount = form.cleaned_data["amount"]
        if amount > summary["balance"]:
            form.add_error("amount", f"El importe supera el saldo pendiente ({summary['balance']}).")
        else:
            remaining = amount
            allocations = []
            for installment in document.installments.order_by("due_date", "sequence"):
                pending = installment.amount - installment_paid_amount(installment)
                applied = min(remaining, pending)
                if applied > 0:
                    allocations.append({"installment": installment, "amount": applied})
                    remaining -= applied
                if remaining <= 0:
                    break
            try:
                payment = register_supplier_payment(
                    company_id=company_id, store=store, supplier=document.supplier,
                    payment_number=form.cleaned_data["payment_number"],
                    payment_date=form.cleaned_data["payment_date"], currency=document.currency,
                    exchange_rate=document.exchange_rate,
                    means_of_payment=form.cleaned_data["means_of_payment"], allocations=allocations,
                    reference=form.cleaned_data.get("reference", ""), notes=form.cleaned_data.get("notes", ""),
                    created_by=request.user,
                )
            except IntegrityError:
                form.add_error("payment_number", "Ya existe un pago con este numero.")
            except ValueError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, f"Pago {payment.payment_number} registrado correctamente.")
                if request.POST.get("next") == "list":
                    return redirect("purchases:document_list")
                return redirect("purchases:document_detail", pk=document.pk)
    return render(request, "purchases/payment_form.html", {
        "form": form, "purchase_document": document, "payment_summary": summary,
    })


@require_POST
def supplier_payment_cancel(request, pk):
    denied = _require_permission(request, "authorize")
    if denied:
        return denied
    company_id, store = _active_scope(request)
    try:
        payment = SupplierPayment.objects.prefetch_related(
            "allocations__installment"
        ).get(pk=pk, company_id=company_id, store_id=store.pk)
    except SupplierPayment.DoesNotExist:
        raise Http404
    document_id = payment.allocations.first().installment.purchase_document_id
    cancel_supplier_payment(payment.pk, company_id=company_id, cancelled_by=request.user)
    messages.success(request, "Pago anulado y saldos recalculados.")
    return redirect("purchases:document_detail", pk=document_id)


def accounts_payable_list(request):
    denied = _require_permission(request, "read")
    if denied:
        return denied
    company_id, store = _active_scope(request)
    supplier_id = request.GET.get("supplier", "")
    documents = PurchaseDocument.objects.filter(
        company_id=company_id, store_id=store.pk,
        document_status=PurchaseDocumentStatus.REGISTERED,
    ).select_related("supplier", "document_type").prefetch_related("installments")
    if supplier_id:
        documents = documents.filter(supplier_id=supplier_id)
    rows = []
    for document in documents.order_by("due_date", "issue_date"):
        summary = document_payment_summary(document)
        if summary["balance"] > 0:
            rows.append({
                "document": document, **summary,
                "due_date": document.due_date or document.issue_date,
                "overdue": (document.due_date or document.issue_date) < timezone.localdate(),
            })
    return render(request, "purchases/accounts_payable_list.html", {
        "rows": rows, "suppliers": Supplier.objects.filter(company_id=company_id, active=True).order_by("name"),
        "supplier_id": supplier_id,
    })


def purchase_installment_schedule(request, document_pk):
    denied = _require_permission(request, "manage")
    if denied:
        return denied
    company_id, _ = _active_scope(request)
    document = _document_or_404(request, document_pk)
    initial = [{"due_date": item.due_date, "amount": item.amount} for item in document.installments.all()]
    formset = PurchaseInstallmentFormSet(
        request.POST or None, prefix="installments",
        initial=None if request.method == "POST" else initial,
    )
    if request.method == "POST" and formset.is_valid():
        try:
            replace_installment_schedule(
                document.pk, company_id=company_id,
                schedule=[form.cleaned_data for form in formset if form.cleaned_data],
            )
        except ValueError as exc:
            formset._non_form_errors = formset.error_class([str(exc)])
        else:
            messages.success(request, "Programacion de cuotas actualizada.")
            return redirect("purchases:document_detail", pk=document.pk)
    return render(request, "purchases/installment_form.html", {
        "formset": formset, "purchase_document": document,
    })


def purchase_landed_cost_create(request, document_pk):
    denied = _require_permission(request, "manage")
    if denied:
        return denied
    company_id, _ = _active_scope(request)
    document = _document_or_404(request, document_pk)
    eligible_lines = list(document.lines.select_related("product").filter(
        product__isnull=False, product__tracks_inventory=True
    ).order_by("position"))
    initial_allocations = [{"line": line.pk, "amount": 0} for line in eligible_lines]
    form = PurchaseLandedCostForm(request.POST or None)
    formset = PurchaseLandedCostAllocationFormSet(
        request.POST or None, prefix="allocations",
        initial=None if request.method == "POST" else initial_allocations,
        form_kwargs={"document": document},
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        try:
            allocate_landed_cost(
                document_id=document.pk, company_id=company_id,
                description=form.cleaned_data["description"], reference=form.cleaned_data.get("reference", ""),
                amount=form.cleaned_data["amount"], allocation_method=form.cleaned_data["allocation_method"],
                manual_allocations=[line.cleaned_data for line in formset if line.cleaned_data],
                notes=form.cleaned_data.get("notes", ""), created_by=request.user,
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Cargo adicional distribuido correctamente.")
            return redirect("purchases:document_detail", pk=document.pk)
    return render(request, "purchases/landed_cost_form.html", {
        "form": form, "formset": formset, "purchase_document": document,
        "allocation_rows": zip(formset.forms, eligible_lines),
    })


@require_POST
def purchase_landed_cost_cancel(request, pk):
    denied = _require_permission(request, "authorize")
    if denied:
        return denied
    company_id, store = _active_scope(request)
    try:
        landed_cost = PurchaseLandedCost.objects.select_related("purchase_document").get(
            pk=pk, purchase_document__company_id=company_id, purchase_document__store_id=store.pk
        )
    except PurchaseLandedCost.DoesNotExist:
        raise Http404
    cancel_landed_cost(landed_cost.pk, company_id=company_id, cancelled_by=request.user)
    messages.success(request, "Cargo adicional anulado.")
    return redirect("purchases:document_detail", pk=landed_cost.purchase_document_id)
