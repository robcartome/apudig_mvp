"""
inventory/views/masters.py — CRUDs de maestros de inventario.

Patrón por entidad:
  List  → GET  /inventory/<entidad>/
  Create → GET+POST /inventory/<entidad>/nueva/
  Update → GET+POST /inventory/<entidad>/<pk>/editar/
  Delete → POST     /inventory/<entidad>/<pk>/eliminar/
"""
from django.contrib import messages
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView

from apps.core.mixins import ActiveCompanyRequiredMixin, CompanyScopedMixin
from apps.companies.models import Store

from ..forms import BrandForm, CategoryForm, ProductForm, UnitForm, WarehouseForm, WarehouseLocationForm
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


# ══════════════════════════════════════════════════════════════════════════════
# CATEGORIES
# ══════════════════════════════════════════════════════════════════════════════

def category_list(request):
    if not request.user.is_authenticated:
        from django.shortcuts import redirect as _r
        return _r("login")
    query = request.GET.get("q", "")
    qs = search_categories(query) if query else get_categories()
    page_obj = _paginate(request, qs)
    return render(request, "inventory/category_list.html", {
        "page_obj": page_obj, "query": query,
    })


def category_create(request):
    if not request.user.is_authenticated:
        return redirect("login")
    form = CategoryForm(request.POST or None)
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
    obj = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST or None, instance=obj)
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
    obj = get_object_or_404(Category, pk=pk)
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
    query = request.GET.get("q", "")
    qs = search_brands(query) if query else get_brands()
    page_obj = _paginate(request, qs)
    return render(request, "inventory/brand_list.html", {
        "page_obj": page_obj, "query": query,
    })


def brand_create(request):
    if not request.user.is_authenticated:
        return redirect("login")
    form = BrandForm(request.POST or None)
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
    obj = get_object_or_404(Brand, pk=pk)
    form = BrandForm(request.POST or None, instance=obj)
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
    obj = get_object_or_404(Brand, pk=pk)
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
    query = request.GET.get("q", "")
    qs = search_products(query) if query else get_products()
    page_obj = _paginate(request, qs)
    return render(request, "inventory/product_list.html", {
        "page_obj": page_obj, "query": query,
    })


def product_create(request):
    if not request.user.is_authenticated:
        return redirect("login")
    form = ProductForm(request.POST or None)
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
    obj = get_object_or_404(Product, pk=pk)
    form = ProductForm(request.POST or None, instance=obj)
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
    obj = get_object_or_404(Product, pk=pk)
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
