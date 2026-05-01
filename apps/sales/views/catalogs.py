"""
sales/views/catalogs.py — CRUD de catálogos documentales:
  · DocumentSeries (series por empresa/sucursal/tipo)
  · BusinessDocumentType (tipos de documento comercial)
"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render

from apps.sales.forms import BusinessDocumentTypeForm, DocumentSeriesForm
from apps.sales.models import BusinessDocumentType, DocumentSeries
from apps.sales.selectors import get_active_document_types, get_series_for_store
from apps.sales.services import create_document_series, toggle_series


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_auth(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return None


def _get_ids(request):
    company_id = getattr(request, "active_company_id", None) or request.session.get("active_company_id")
    store_id = getattr(request, "active_store_id", None) or request.session.get("active_store_id")
    return company_id, store_id


# ── Document Series ───────────────────────────────────────────────────────────

def series_list(request):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    company_id, store_id = _get_ids(request)
    qs = (
        DocumentSeries.objects
        .select_related("store", "company")
        .filter(company_id=company_id)
        .order_by("voucher_type", "series")
    )

    voucher_type = request.GET.get("type", "")
    if voucher_type:
        qs = qs.filter(voucher_type=voucher_type)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    from apps.sales.models import VOUCHER_TYPE_CHOICES
    return render(request, "sales/series_list.html", {
        "page_obj": page_obj,
        "voucher_type": voucher_type,
        "type_choices": VOUCHER_TYPE_CHOICES,
    })


def series_create(request):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    company_id, store_id = _get_ids(request)

    if request.method == "POST":
        form = DocumentSeriesForm(request.POST, company_id=company_id, store_id=store_id)
        if form.is_valid():
            try:
                create_document_series(
                    company_id=company_id,
                    store_id=str(form.cleaned_data["store"].pk) if form.cleaned_data.get("store") else None,
                    voucher_type=form.cleaned_data["voucher_type"],
                    series_code=form.cleaned_data["series"],
                )
                messages.success(request, "Serie creada correctamente.")
                return redirect("sales:series_list")
            except ValueError as exc:
                form.add_error("series", str(exc))
    else:
        form = DocumentSeriesForm(company_id=company_id, store_id=store_id)

    return render(request, "sales/series_form.html", {"form": form, "title": "Nueva serie"})


def series_update(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    company_id, store_id = _get_ids(request)
    obj = get_object_or_404(DocumentSeries, pk=pk, company_id=company_id)

    if request.method == "POST":
        form = DocumentSeriesForm(request.POST, instance=obj, company_id=company_id, store_id=store_id)
        if form.is_valid():
            form.save()
            messages.success(request, "Serie actualizada.")
            return redirect("sales:series_list")
    else:
        form = DocumentSeriesForm(instance=obj, company_id=company_id, store_id=store_id)

    return render(request, "sales/series_form.html", {"form": form, "title": "Editar serie", "obj": obj})


def series_toggle(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    if request.method != "POST":
        return redirect("sales:series_list")

    company_id, _ = _get_ids(request)
    obj = get_object_or_404(DocumentSeries, pk=pk, company_id=company_id)
    toggle_series(obj)
    state = "activada" if obj.active else "desactivada"
    messages.success(request, f"Serie {obj.series} {state}.")
    return redirect("sales:series_list")


# ── Business Document Types ───────────────────────────────────────────────────

def doctype_list(request):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    qs = BusinessDocumentType.objects.all().order_by("code")
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "sales/doctype_list.html", {"page_obj": page_obj})


def doctype_create(request):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    if request.method == "POST":
        form = BusinessDocumentTypeForm(request.POST)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Tipo de documento creado.")
                return redirect("sales:doctype_list")
            except IntegrityError:
                form.add_error("code", "Ya existe un tipo con ese código.")
    else:
        form = BusinessDocumentTypeForm()

    return render(request, "sales/doctype_form.html", {"form": form, "title": "Nuevo tipo de documento"})


def doctype_update(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp

    obj = get_object_or_404(BusinessDocumentType, pk=pk)

    if request.method == "POST":
        form = BusinessDocumentTypeForm(request.POST, instance=obj)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Tipo de documento actualizado.")
                return redirect("sales:doctype_list")
            except IntegrityError:
                form.add_error("code", "Ya existe un tipo con ese código.")
    else:
        form = BusinessDocumentTypeForm(instance=obj)

    return render(request, "sales/doctype_form.html", {"form": form, "title": "Editar tipo de documento", "obj": obj})
