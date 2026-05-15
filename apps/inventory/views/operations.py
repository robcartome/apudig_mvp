"""
inventory/views/operations.py — Vistas de movimientos de stock y consulta de stock.
"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..forms import MovementDetailFormSet, MovementHeaderForm, MovementTransferForm
from ..models import Movement
from ..selectors import (
    get_movement_detail,
    get_movements_for_store,
    get_stock_by_warehouse,
    get_warehouses_for_store,
    search_movements,
)
from ..services import register_entry, register_exit, register_transfer
from ..services import delete_movement, update_movement


def _require_auth(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return None


def _get_store_id(request):
    return getattr(request, "active_store_id", None) or request.session.get("active_store_id")


def _paginate(request, qs, per_page: int = 25):
    return Paginator(qs, per_page).get_page(request.GET.get("page", 1))


def _parse_lines(formset):
    """Extrae líneas válidas del formset de detalles."""
    lines = []
    for f in formset:
        if f.is_valid() and f.cleaned_data and not f.cleaned_data.get("DELETE", False):
            lines.append({
                "product_id": f.cleaned_data["product"].pk,
                "quantity": f.cleaned_data["quantity"],
                "unit_price": f.cleaned_data.get("unit_price", 0),
            })
    return lines

def stock_report(request):
    r = _require_auth(request)
    if r:
        return r
    store_id = _get_store_id(request)
    warehouses = get_warehouses_for_store(store_id, active_only=True) if store_id else []
    selected_warehouse = request.GET.get("warehouse", "")
    stocks = get_stock_by_warehouse(store_id) if store_id else []
    if selected_warehouse:
        stocks = stocks.filter(warehouse_id=selected_warehouse)
    return render(request, "inventory/stock_report.html", {
        "stocks": stocks,
        "warehouses": warehouses,
        "selected_warehouse": selected_warehouse,
    })

def movement_list(request):
    r = _require_auth(request)
    if r:
        return r
    store_id = _get_store_id(request)
    query = request.GET.get("q", "")
    movement_type = request.GET.get("type", "")
    qs = search_movements(store_id, query, movement_type or None) if store_id else Movement.objects.none()
    page_obj = _paginate(request, qs)
    return render(request, "inventory/movement_list.html", {
        "page_obj": page_obj,
        "query": query,
        "movement_type": movement_type,
        "type_choices": Movement.MOVEMENT_TYPES,
    })


def movement_detail(request, pk):
    r = _require_auth(request)
    if r:
        return r
    try:
        movement = get_movement_detail(pk)
    except Movement.DoesNotExist:
        from django.http import Http404
        raise Http404
    return render(request, "inventory/movement_detail.html", {"movement": movement})


def _get_movement_for_store_or_404(pk, store_id):
    return get_object_or_404(
        Movement.objects.prefetch_related("details"),
        pk=pk,
        store_id=store_id,
    )


def _movement_forms(request, store_id, movement):
    initial_lines = [
        {
            "product": d.product_id,
            "quantity": d.quantity,
            "unit_price": d.unit_price,
        }
        for d in movement.details.all()
    ]

    if movement.type == "TRANSFER":
        form = MovementTransferForm(request.POST or None, store_id=store_id, instance=movement)
    else:
        form = MovementHeaderForm(
            request.POST or None,
            store_id=store_id,
            movement_type=movement.type,
            instance=movement,
        )

    formset = MovementDetailFormSet(request.POST or None, initial=initial_lines, prefix="lines")
    return form, formset


def movement_edit(request, pk):
    r = _require_auth(request)
    if r:
        return r

    store_id = _get_store_id(request)
    movement = _get_movement_for_store_or_404(pk, store_id)
    form, formset = _movement_forms(request, store_id, movement)

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        lines = _parse_lines(formset)
        if not lines:
            messages.error(request, "Debe agregar al menos un producto.")
        else:
            cd = form.cleaned_data
            update_data = {
                "date": cd["date"],
                "reason": cd.get("reason", ""),
                "reference_doc": cd.get("reference_doc", ""),
            }

            if movement.type == "TRANSFER":
                update_data.update({
                    "warehouse": None,
                    "warehouse_origin": cd["warehouse_origin"],
                    "warehouse_dest": cd["warehouse_dest"],
                    "supplier": None,
                    "customer": None,
                    "document_type": None,
                    "carrier": None,
                })
            elif movement.type == "ENTRY":
                update_data.update({
                    "warehouse": cd["warehouse"],
                    "warehouse_origin": None,
                    "warehouse_dest": None,
                    "supplier": cd.get("supplier"),
                    "customer": None,
                    "document_type": cd.get("document_type"),
                    "carrier": cd.get("carrier"),
                })
            elif movement.type == "EXIT":
                update_data.update({
                    "warehouse": cd["warehouse"],
                    "warehouse_origin": None,
                    "warehouse_dest": None,
                    "supplier": None,
                    "customer": cd.get("customer"),
                    "document_type": cd.get("document_type"),
                    "carrier": cd.get("carrier"),
                })

            update_movement(movement, lines=lines, **update_data)
            messages.success(request, "Movimiento actualizado correctamente.")
            return redirect("inventory:movement_list")

    return render(request, "inventory/movement_form.html", {
        "form": form,
        "formset": formset,
        "title": f"Editar {movement.get_type_display().lower()}",
        "movement_type": movement.type,
        "cancel_url": "inventory:movement_list",
        "is_edit": True,
        "movement": movement,
    })


def movement_delete(request, pk):
    r = _require_auth(request)
    if r:
        return r

    store_id = _get_store_id(request)
    movement = _get_movement_for_store_or_404(pk, store_id)

    if request.method == "POST":
        delete_movement(movement)
        messages.success(request, "Movimiento eliminado correctamente.")
        return redirect("inventory:movement_list")

    return render(request, "inventory/confirm_delete.html", {
        "object": movement,
        "cancel_url": "inventory:movement_list",
    })


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY
# ══════════════════════════════════════════════════════════════════════════════

def entry_create(request):
    r = _require_auth(request)
    if r:
        return r
    store_id = _get_store_id(request)
    form = MovementHeaderForm(
        request.POST or None, store_id=store_id, movement_type="ENTRY",
        initial={"date": timezone.now().strftime("%Y-%m-%dT%H:%M")},
    )
    formset = MovementDetailFormSet(request.POST or None, prefix="lines")

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        lines = _parse_lines(formset)
        if not lines:
            messages.error(request, "Debe agregar al menos un producto.")
        else:
            cd = form.cleaned_data
            register_entry(
                store_id=store_id,
                warehouse_id=str(cd["warehouse"].pk),
                date=cd["date"],
                lines=lines,
                created_by=request.user,
                reason=cd.get("reason", ""),
                reference_doc=cd.get("reference_doc", ""),
                supplier_id=cd["supplier"].pk if cd.get("supplier") else None,
                document_type_id=cd["document_type"].pk if cd.get("document_type") else None,
            )
            messages.success(request, "Entrada registrada correctamente.")
            return redirect("inventory:movement_list")

    return render(request, "inventory/movement_form.html", {
        "form": form,
        "formset": formset,
        "title": "Nueva entrada",
        "movement_type": "ENTRY",
        "cancel_url": "inventory:movement_list",
    })


# ══════════════════════════════════════════════════════════════════════════════
# EXIT
# ══════════════════════════════════════════════════════════════════════════════

def exit_create(request):
    r = _require_auth(request)
    if r:
        return r
    store_id = _get_store_id(request)
    form = MovementHeaderForm(
        request.POST or None, store_id=store_id, movement_type="EXIT",
        initial={"date": timezone.now().strftime("%Y-%m-%dT%H:%M")},
    )
    formset = MovementDetailFormSet(request.POST or None, prefix="lines")

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        lines = _parse_lines(formset)
        if not lines:
            messages.error(request, "Debe agregar al menos un producto.")
        else:
            cd = form.cleaned_data
            register_exit(
                store_id=store_id,
                warehouse_id=str(cd["warehouse"].pk),
                date=cd["date"],
                lines=lines,
                created_by=request.user,
                reason=cd.get("reason", ""),
                reference_doc=cd.get("reference_doc", ""),
                customer_id=cd["customer"].pk if cd.get("customer") else None,
                document_type_id=cd["document_type"].pk if cd.get("document_type") else None,
            )
            messages.success(request, "Salida registrada correctamente.")
            return redirect("inventory:movement_list")

    return render(request, "inventory/movement_form.html", {
        "form": form,
        "formset": formset,
        "title": "Nueva salida",
        "movement_type": "EXIT",
        "cancel_url": "inventory:movement_list",
    })


# ══════════════════════════════════════════════════════════════════════════════
# TRANSFER
# ══════════════════════════════════════════════════════════════════════════════

def transfer_create(request):
    r = _require_auth(request)
    if r:
        return r
    store_id = _get_store_id(request)
    form = MovementTransferForm(
        request.POST or None, store_id=store_id,
        initial={"date": timezone.now().strftime("%Y-%m-%dT%H:%M")},
    )
    formset = MovementDetailFormSet(request.POST or None, prefix="lines")

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        lines = _parse_lines(formset)
        if not lines:
            messages.error(request, "Debe agregar al menos un producto.")
        else:
            cd = form.cleaned_data
            register_transfer(
                store_id=store_id,
                warehouse_origin_id=str(cd["warehouse_origin"].pk),
                warehouse_dest_id=str(cd["warehouse_dest"].pk),
                date=cd["date"],
                lines=lines,
                created_by=request.user,
                reason=cd.get("reason", ""),
                reference_doc=cd.get("reference_doc", ""),
            )
            messages.success(request, "Transferencia registrada correctamente.")
            return redirect("inventory:movement_list")

    return render(request, "inventory/movement_form.html", {
        "form": form,
        "formset": formset,
        "title": "Nueva transferencia",
        "movement_type": "TRANSFER",
        "cancel_url": "inventory:movement_list",
    })
