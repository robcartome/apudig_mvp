"""
inventory/views/masters.py — CRUDs de maestros de inventario.

Patrón por entidad:
  List  → GET  /inventory/<entidad>/
  Create → GET+POST /inventory/<entidad>/nueva/
  Update → GET+POST /inventory/<entidad>/<pk>/editar/
  Delete → POST     /inventory/<entidad>/<pk>/eliminar/
"""
import csv
import io
from uuid import uuid4

from django.contrib import messages
from django.db import models
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView

from apps.core.mixins import ActiveCompanyRequiredMixin, CompanyScopedMixin
from apps.companies.models import Company, Store

from ..forms import BulkImportForm, BrandForm, CategoryForm, ProductForm, UnitForm, WarehouseForm, WarehouseLocationForm
from ..importers import (
    ENTITY_LABELS,
    build_import_template_workbook,
    import_inventory_excel,
)
from ..models import Brand, Category, Product, Unit, Warehouse, WarehouseLocation
from ..selectors import (
    get_brands,
    get_categories,
    get_products,
    get_units,
    get_warehouses_for_store,
    search_brands,
    search_categories,
    search_products,
    search_units,
    search_warehouses,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _paginate(request, qs, per_page: int = 25):
    from django.core.paginator import Paginator
    paginator = Paginator(qs, per_page)
    page = request.GET.get("page", 1)
    return paginator.get_page(page)


def _require_company(request):
    """Returns (Company instance, None) or (None, redirect_response) if no active company."""
    company_id = (
        getattr(request, "active_company_id", None)
        or request.session.get("active_company_id")
    )
    if not company_id:
        messages.error(request, "Selecciona una empresa antes de continuar.")
        return None, redirect("select_company")
    try:
        return Company.objects.get(pk=company_id), None
    except Company.DoesNotExist:
        messages.error(request, "Empresa no encontrada.")
        return None, redirect("select_company")


def bulk_import(request, entity: str):
    if not request.user.is_authenticated:
        return redirect("login")

    if entity not in ENTITY_LABELS:
        messages.error(request, "Tipo de importacion no valido.")
        return redirect("inventory:product_list")

    company = None
    if entity in {"categories", "brands", "products"}:
        company, err = _require_company(request)
        if err:
            return err

    label = ENTITY_LABELS[entity]
    form = BulkImportForm(request.POST or None, request.FILES or None)
    error_token = ""

    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["file"]
        dry_run = bool(form.cleaned_data.get("dry_run"))
        try:
            result = import_inventory_excel(
                entity=entity,
                file_obj=upload,
                filename=upload.name,
                company=company,
                dry_run=dry_run,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        except Exception as exc:
            messages.error(request, f"Error al procesar archivo: {exc}")
        else:
            prefix = "Validacion" if dry_run else "Importacion"
            if result.errors:
                buffer = io.StringIO()
                writer = csv.writer(buffer)
                writer.writerow(["error"])
                for err_line in result.errors:
                    writer.writerow([err_line])
                error_token = uuid4().hex
                request.session[f"inventory_bulk_errors_{error_token}"] = buffer.getvalue()

                messages.error(
                    request,
                    f"{prefix} con errores para {label}. Filas: {result.total_rows}. "
                    f"Creados: {result.created}. Actualizados: {result.updated}. "
                    f"Errores: {len(result.errors)}.",
                )
                for err_line in result.errors[:20]:
                    messages.warning(request, err_line)
                if len(result.errors) > 20:
                    messages.warning(request, f"Se omitieron {len(result.errors) - 20} errores adicionales.")
            else:
                messages.success(
                    request,
                    f"{prefix} OK para {label}. Filas: {result.total_rows}. "
                    f"Creados: {result.created}. Actualizados: {result.updated}.",
                )

    return render(request, "inventory/bulk_import.html", {
        "form": form,
        "entity": entity,
        "entity_label": label,
        "error_token": error_token,
    })


def bulk_import_template(request, entity: str):
    if not request.user.is_authenticated:
        return redirect("login")

    if entity not in ENTITY_LABELS:
        messages.error(request, "Tipo de importacion no valido.")
        return redirect("inventory:product_list")

    if entity in {"categories", "brands", "products"}:
        _, err = _require_company(request)
        if err:
            return err

    content = build_import_template_workbook(entity)
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="plantilla_{entity}.xlsx"'
    return response


def bulk_import_errors(request, token: str):
    if not request.user.is_authenticated:
        return redirect("login")

    key = f"inventory_bulk_errors_{token}"
    csv_content = request.session.get(key)
    if not csv_content:
        messages.error(request, "El reporte de errores ya no esta disponible.")
        return redirect("inventory:product_list")

    del request.session[key]
    response = HttpResponse(csv_content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="import_errors.csv"'
    return response


# ══════════════════════════════════════════════════════════════════════════════
# CATEGORIES
# ══════════════════════════════════════════════════════════════════════════════

def category_list(request):
    if not request.user.is_authenticated:
        from django.shortcuts import redirect as _r
        return _r("login")
    company, err = _require_company(request)
    if err:
        return err
    query = request.GET.get("q", "")
    qs = search_categories(query, company_id=company.pk) if query else get_categories(company_id=company.pk)
    page_obj = _paginate(request, qs)
    return render(request, "inventory/category_list.html", {
        "page_obj": page_obj, "query": query,
    })


def category_create(request):
    if not request.user.is_authenticated:
        return redirect("login")
    company, err = _require_company(request)
    if err:
        return err
    form = CategoryForm(request.POST or None, company=company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Categoría creada correctamente.")
        return redirect("inventory:category_list")
    return render(request, "inventory/category_form.html", {
        "form": form, "title": "Nueva categoría", "cancel_url": "inventory:category_list",
    })


def category_update(request, pk):
    if not request.user.is_authenticated:
        return redirect("login")
    company, err = _require_company(request)
    if err:
        return err
    obj = get_object_or_404(Category, pk=pk, company=company)
    form = CategoryForm(request.POST or None, instance=obj, company=company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Categoría actualizada.")
        return redirect("inventory:category_list")
    return render(request, "inventory/category_form.html", {
        "form": form, "title": "Editar categoría", "object": obj, "cancel_url": "inventory:category_list",
    })


def category_delete(request, pk):
    if not request.user.is_authenticated:
        return redirect("login")
    company, err = _require_company(request)
    if err:
        return err
    obj = get_object_or_404(Category, pk=pk, company=company)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Categoría eliminada.")
        return redirect("inventory:category_list")
    return render(request, "inventory/confirm_delete.html", {
        "object": obj, "cancel_url": "inventory:category_list",
    })


# ══════════════════════════════════════════════════════════════════════════════
# BRANDS
# ══════════════════════════════════════════════════════════════════════════════

def brand_list(request):
    if not request.user.is_authenticated:
        return redirect("login")
    company, err = _require_company(request)
    if err:
        return err
    query = request.GET.get("q", "")
    qs = search_brands(query, company_id=company.pk) if query else get_brands(company_id=company.pk)
    page_obj = _paginate(request, qs)
    return render(request, "inventory/brand_list.html", {
        "page_obj": page_obj, "query": query,
    })


def brand_create(request):
    if not request.user.is_authenticated:
        return redirect("login")
    company, err = _require_company(request)
    if err:
        return err
    form = BrandForm(request.POST or None, company=company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Marca creada correctamente.")
        return redirect("inventory:brand_list")
    return render(request, "inventory/brand_form.html", {
        "form": form, "title": "Nueva marca", "cancel_url": "inventory:brand_list",
    })


def brand_update(request, pk):
    if not request.user.is_authenticated:
        return redirect("login")
    company, err = _require_company(request)
    if err:
        return err
    obj = get_object_or_404(Brand, pk=pk, company=company)
    form = BrandForm(request.POST or None, instance=obj, company=company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Marca actualizada.")
        return redirect("inventory:brand_list")
    return render(request, "inventory/brand_form.html", {
        "form": form, "title": "Editar marca", "object": obj, "cancel_url": "inventory:brand_list",
    })


def brand_delete(request, pk):
    if not request.user.is_authenticated:
        return redirect("login")
    company, err = _require_company(request)
    if err:
        return err
    obj = get_object_or_404(Brand, pk=pk, company=company)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Marca eliminada.")
        return redirect("inventory:brand_list")
    return render(request, "inventory/confirm_delete.html", {
        "object": obj, "cancel_url": "inventory:brand_list",
    })


# ══════════════════════════════════════════════════════════════════════════════
# UNITS
# ══════════════════════════════════════════════════════════════════════════════

def unit_list(request):
    if not request.user.is_authenticated:
        return redirect("login")
    query = request.GET.get("q", "")
    qs = search_units(query) if query else get_units()
    page_obj = _paginate(request, qs)
    return render(request, "inventory/unit_list.html", {
        "page_obj": page_obj, "query": query,
    })


def unit_create(request):
    if not request.user.is_authenticated:
        return redirect("login")
    form = UnitForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Unidad creada correctamente.")
        return redirect("inventory:unit_list")
    return render(request, "inventory/unit_form.html", {
        "form": form, "title": "Nueva unidad", "cancel_url": "inventory:unit_list",
    })


def unit_update(request, pk):
    if not request.user.is_authenticated:
        return redirect("login")
    obj = get_object_or_404(Unit, pk=pk)
    form = UnitForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Unidad actualizada.")
        return redirect("inventory:unit_list")
    return render(request, "inventory/unit_form.html", {
        "form": form, "title": "Editar unidad", "object": obj, "cancel_url": "inventory:unit_list",
    })


def unit_delete(request, pk):
    if not request.user.is_authenticated:
        return redirect("login")
    obj = get_object_or_404(Unit, pk=pk)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Unidad eliminada.")
        except Exception:
            messages.error(request, "No se puede eliminar: tiene productos asociados.")
        return redirect("inventory:unit_list")
    return render(request, "inventory/confirm_delete.html", {
        "object": obj, "cancel_url": "inventory:unit_list",
    })


# ══════════════════════════════════════════════════════════════════════════════
# WAREHOUSES  (scoped por store activa)
# ══════════════════════════════════════════════════════════════════════════════

def _require_store(request):
    """Devuelve store_id o None si no hay sucursal activa."""
    return getattr(request, "active_store_id", None)


def warehouse_list(request):
    if not request.user.is_authenticated:
        return redirect("login")
    store_id = _require_store(request)
    query = request.GET.get("q", "")
    if store_id:
        qs = search_warehouses(store_id, query) if query else get_warehouses_for_store(store_id)
    else:
        qs = Warehouse.objects.none()
    page_obj = _paginate(request, qs)
    return render(request, "inventory/warehouse_list.html", {
        "page_obj": page_obj, "query": query, "no_store": store_id is None,
    })


def warehouse_create(request):
    if not request.user.is_authenticated:
        return redirect("login")
    store_id = _require_store(request)
    form = WarehouseForm(request.POST or None, store=store_id)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Almacén creado correctamente.")
        return redirect("inventory:warehouse_list")
    return render(request, "inventory/warehouse_form.html", {
        "form": form, "title": "Nuevo almacén", "cancel_url": "inventory:warehouse_list",
    })


def warehouse_update(request, pk):
    if not request.user.is_authenticated:
        return redirect("login")
    store_id = _require_store(request)
    obj = get_object_or_404(Warehouse, pk=pk, store_id=store_id)
    form = WarehouseForm(request.POST or None, instance=obj, store=store_id)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Almacén actualizado.")
        return redirect("inventory:warehouse_list")
    return render(request, "inventory/warehouse_form.html", {
        "form": form, "title": "Editar almacén", "object": obj, "cancel_url": "inventory:warehouse_list",
    })


def warehouse_delete(request, pk):
    if not request.user.is_authenticated:
        return redirect("login")
    store_id = _require_store(request)
    obj = get_object_or_404(Warehouse, pk=pk, store_id=store_id)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Almacén eliminado.")
        except Exception:
            messages.error(request, "No se puede eliminar: tiene stock registrado.")
        return redirect("inventory:warehouse_list")
    return render(request, "inventory/confirm_delete.html", {
        "object": obj, "cancel_url": "inventory:warehouse_list",
    })


# ══════════════════════════════════════════════════════════════════════════════
# PRODUCTS  (listado + alta; detalle y movimientos en Parte 4)
# ══════════════════════════════════════════════════════════════════════════════

def product_list(request):
    if not request.user.is_authenticated:
        return redirect("login")
    company, err = _require_company(request)
    if err:
        return err
    query = request.GET.get("q", "")
    qs = search_products(query, company_id=company.pk) if query else get_products(company_id=company.pk)
    page_obj = _paginate(request, qs)
    return render(request, "inventory/product_list.html", {
        "page_obj": page_obj, "query": query,
    })


def product_create(request):
    if not request.user.is_authenticated:
        return redirect("login")
    company, err = _require_company(request)
    if err:
        return err
    form = ProductForm(request.POST or None, company=company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Producto creado correctamente.")
        return redirect("inventory:product_list")
    return render(request, "inventory/product_form.html", {
        "form": form, "title": "Nuevo producto", "cancel_url": "inventory:product_list",
    })


def product_update(request, pk):
    if not request.user.is_authenticated:
        return redirect("login")
    company, err = _require_company(request)
    if err:
        return err
    obj = get_object_or_404(Product, pk=pk, company=company)
    form = ProductForm(request.POST or None, instance=obj, company=company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Producto actualizado.")
        return redirect("inventory:product_list")
    return render(request, "inventory/product_form.html", {
        "form": form, "title": "Editar producto", "object": obj, "cancel_url": "inventory:product_list",
    })


def product_delete(request, pk):
    if not request.user.is_authenticated:
        return redirect("login")
    company, err = _require_company(request)
    if err:
        return err
    obj = get_object_or_404(Product, pk=pk, company=company)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Producto eliminado.")
        except Exception:
            messages.error(request, "No se puede eliminar: tiene stock o movimientos asociados.")
        return redirect("inventory:product_list")
    return render(request, "inventory/confirm_delete.html", {
        "object": obj, "cancel_url": "inventory:product_list",
    })


def warehouse_location_list(request):
    if not request.user.is_authenticated:
        return redirect("login")
    store_id = _require_store(request)
    warehouse_id = request.GET.get("warehouse", "")
    query = request.GET.get("q", "")

    warehouses = Warehouse.objects.filter(store_id=store_id, active=True).order_by("name") if store_id else Warehouse.objects.none()

    qs = WarehouseLocation.objects.select_related("warehouse")
    if store_id:
        qs = qs.filter(warehouse__store_id=store_id)
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)
    if query:
        qs = qs.filter(models.Q(code__icontains=query) | models.Q(name__icontains=query))
    qs = qs.order_by("warehouse__name", "code")

    page_obj = _paginate(request, qs)
    return render(request, "inventory/warehouse_location_list.html", {
        "page_obj": page_obj,
        "warehouses": warehouses,
        "selected_warehouse": warehouse_id,
        "query": query,
    })


def warehouse_location_create(request):
    if not request.user.is_authenticated:
        return redirect("login")
    store_id = _require_store(request)
    form = WarehouseLocationForm(request.POST or None, store_id=store_id)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Ubicación creada correctamente.")
        return redirect("inventory:warehouse_location_list")
    return render(request, "inventory/warehouse_location_form.html", {
        "form": form, "title": "Nueva ubicación en bodega", "cancel_url": "inventory:warehouse_location_list",
    })


def warehouse_location_update(request, pk):
    if not request.user.is_authenticated:
        return redirect("login")
    store_id = _require_store(request)
    obj = get_object_or_404(WarehouseLocation, pk=pk)
    form = WarehouseLocationForm(request.POST or None, instance=obj, store_id=store_id)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Ubicación actualizada.")
        return redirect("inventory:warehouse_location_list")
    return render(request, "inventory/warehouse_location_form.html", {
        "form": form, "title": "Editar ubicación", "object": obj, "cancel_url": "inventory:warehouse_location_list",
    })


def warehouse_location_delete(request, pk):
    if not request.user.is_authenticated:
        return redirect("login")
    obj = get_object_or_404(WarehouseLocation, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Ubicación eliminada.")
        return redirect("inventory:warehouse_location_list")
    return render(request, "inventory/confirm_delete.html", {
        "object": obj, "cancel_url": "inventory:warehouse_location_list",
    })

def admin_panel(request):
    if not request.user.is_authenticated:
        return redirect("login")
    store_id = _require_store(request)
    store = Store.objects.filter(pk=store_id).first() if store_id else None

    if request.method == "POST" and store:
        lock_enabled = request.POST.get("lock_movement_edits") == "on"
        store.lock_movement_edits = lock_enabled
        store.save(update_fields=["lock_movement_edits", "updated_at"])
        messages.success(request, "Configuración de bloqueo de movimientos actualizada.")
        return redirect("inventory:admin_panel")

    warehouse_count = Warehouse.objects.filter(store_id=store_id, active=True).count() if store_id else 0
    location_count = WarehouseLocation.objects.filter(warehouse__store_id=store_id, active=True).count() if store_id else 0
    return render(request, "inventory/admin_panel.html", {
        "warehouse_count": warehouse_count,
        "location_count": location_count,
        "movement_lock_enabled": bool(store.lock_movement_edits) if store else True,
        "active_store": store,
    })
