"""
sales/views/catalogs.py — CRUD de catálogos documentales:
  · DocumentSeries (series por empresa/sucursal/tipo)
  · BusinessDocumentType (tipos de documento comercial)
  · PaymentMethod (formas de pago: Contado, Crédito 30 días)
  · MeansOfPayment (medios de pago: Efectivo, Yape, Plin)
"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from apps.sales.forms import (
    BusinessDocumentTypeForm,
    DocumentSeriesForm,
    PaymentMethodForm,
    MeansOfPaymentForm,
)
from apps.sales.models import BusinessDocumentType, DocumentSeries, PaymentMethod, MeansOfPayment
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


# ── PaymentMethod CRUD (Formas de pago: Contado, Crédito) ────────────────────

def _get_company(request):
    return getattr(request, "active_company_id", None) or request.session.get("active_company_id")


def payment_method_list(request):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp
    company_id = _get_company(request)
    qs = PaymentMethod.objects.filter(company_id=company_id).order_by("name") if company_id else PaymentMethod.objects.none()
    return render(request, "sales/payment_method_list.html", {"objects": qs})


def payment_method_create(request):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp
    company_id = _get_company(request)
    if request.method == "POST":
        form = PaymentMethodForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company_id = company_id
            obj.save()
            messages.success(request, f"Forma de pago «{obj.name}» creada.")
            return redirect("sales:payment_method_list")
    else:
        form = PaymentMethodForm()
    return render(request, "sales/payment_method_form.html", {"form": form, "title": "Nueva forma de pago"})


def payment_method_update(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp
    obj = get_object_or_404(PaymentMethod, pk=pk)
    if request.method == "POST":
        form = PaymentMethodForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f"Forma de pago «{obj.name}» actualizada.")
            return redirect("sales:payment_method_list")
    else:
        form = PaymentMethodForm(instance=obj)
    return render(request, "sales/payment_method_form.html", {"form": form, "title": "Editar forma de pago", "object": obj})


def payment_method_delete(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp
    obj = get_object_or_404(PaymentMethod, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Forma de pago eliminada.")
        return redirect("sales:payment_method_list")
    return render(request, "sales/payment_method_confirm_delete.html", {"object": obj})


# ── PaymentMethod API (Select2 search + quick-create) ────────────────────────

@require_GET
def api_payment_method_search(request):
    if not request.user.is_authenticated:
        return JsonResponse({"results": []}, status=401)
    company_id = _get_company(request)
    q = request.GET.get("q", "").strip()
    qs = PaymentMethod.objects.filter(company_id=company_id, active=True)
    if q:
        qs = qs.filter(name__icontains=q)
    results = [{"id": str(obj.pk), "text": obj.name, "is_cash": obj.is_cash} for obj in qs[:30]]
    return JsonResponse({"results": results})


@require_http_methods(["POST"])
def api_payment_method_create(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    import json
    company_id = _get_company(request)
    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST
    name = (data.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "El nombre es requerido."}, status=400)
    if PaymentMethod.objects.filter(company_id=company_id, name__iexact=name).exists():
        obj = PaymentMethod.objects.get(company_id=company_id, name__iexact=name)
    else:
        obj = PaymentMethod.objects.create(company_id=company_id, name=name)
    return JsonResponse({"id": str(obj.pk), "text": obj.name, "is_cash": obj.is_cash})


# ── MeansOfPayment CRUD (Medios de pago: Efectivo, Yape, Plin) ───────────────

def means_of_payment_list(request):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp
    company_id = _get_company(request)
    qs = MeansOfPayment.objects.filter(company_id=company_id).order_by("name") if company_id else MeansOfPayment.objects.none()
    return render(request, "sales/means_of_payment_list.html", {"objects": qs})


def means_of_payment_create(request):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp
    company_id = _get_company(request)
    if request.method == "POST":
        form = MeansOfPaymentForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company_id = company_id
            obj.save()
            messages.success(request, f"Medio de pago «{obj.name}» creado.")
            return redirect("sales:means_of_payment_list")
    else:
        form = MeansOfPaymentForm()
    return render(request, "sales/means_of_payment_form.html", {"form": form, "title": "Nuevo medio de pago"})


def means_of_payment_update(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp
    obj = get_object_or_404(MeansOfPayment, pk=pk)
    if request.method == "POST":
        form = MeansOfPaymentForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f"Medio de pago «{obj.name}» actualizado.")
            return redirect("sales:means_of_payment_list")
    else:
        form = MeansOfPaymentForm(instance=obj)
    return render(request, "sales/means_of_payment_form.html", {"form": form, "title": "Editar medio de pago", "object": obj})


def means_of_payment_delete(request, pk):
    redirect_resp = _require_auth(request)
    if redirect_resp:
        return redirect_resp
    obj = get_object_or_404(MeansOfPayment, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Medio de pago eliminado.")
        return redirect("sales:means_of_payment_list")
    return render(request, "sales/means_of_payment_confirm_delete.html", {"object": obj})


# ── MeansOfPayment API (Select2 search + quick-create) ───────────────────────

@require_GET
def api_means_of_payment_search(request):
    if not request.user.is_authenticated:
        return JsonResponse({"results": []}, status=401)
    company_id = _get_company(request)
    q = request.GET.get("q", "").strip()
    qs = MeansOfPayment.objects.filter(company_id=company_id, active=True)
    if q:
        qs = qs.filter(name__icontains=q)
    results = [{"id": str(obj.pk), "text": obj.name} for obj in qs[:30]]
    return JsonResponse({"results": results})


@require_http_methods(["POST"])
def api_means_of_payment_create(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    import json
    company_id = _get_company(request)
    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST
    name = (data.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "El nombre es requerido."}, status=400)
    if MeansOfPayment.objects.filter(company_id=company_id, name__iexact=name).exists():
        obj = MeansOfPayment.objects.get(company_id=company_id, name__iexact=name)
    else:
        obj = MeansOfPayment.objects.create(company_id=company_id, name=name)
    return JsonResponse({"id": str(obj.pk), "text": obj.name})


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
