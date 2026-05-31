"""
inventory/views/operations.py — Vistas de movimientos de stock y consulta de stock.
"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..forms import MovementDetailEditFormSet, MovementDetailFormSet, MovementHeaderForm, MovementTransferForm
from ..models import Movement, MovementType, Unit
from ..selectors import (
    get_movement_detail,
    get_movements_for_store,
    get_stock_by_warehouse,
    get_warehouses_for_store,
    search_movements,
)
from ..services import confirm_movement, register_adjustment, register_entry, register_exit, register_transfer
from ..services import delete_movement, update_movement


def _require_auth(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return None


def _get_store_id(request):
    return getattr(request, "active_store_id", None) or request.session.get("active_store_id")


def _get_company_id(request):
    return getattr(request, "active_company_id", None) or request.session.get("active_company_id")


def _require_active_store(request):
    store_id = _get_store_id(request)
    if not store_id:
        messages.error(request, "Debes seleccionar una sucursal activa para registrar movimientos.")
        return None, redirect("select_company")
    return store_id, None


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
                "physical_quantity": f.cleaned_data.get("quantity"),
                "unit_price": f.cleaned_data.get("unit_price", 0),
                "location_id": f.cleaned_data.get("location") or None,
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
        Movement.objects.prefetch_related("details__product__unit"),
        pk=pk,
        store_id=store_id,
    )


def _movement_forms(request, store_id, movement, company_id=None):
    initial_lines = [
        {
            "product":      d.product_id,
            "product_name": d.product.name,
            "product_unit": d.product.unit.code if d.product.unit else "",
            "quantity":     d.physical_quantity if movement.type == MovementType.ADJUSTMENT and d.physical_quantity is not None else d.quantity,
            "unit_price":   d.unit_price,
        }
        for d in movement.details.all()
    ]

    if movement.type == MovementType.TRANSFER:
        form = MovementTransferForm(request.POST or None, store_id=store_id, instance=movement)
    else:
        form = MovementHeaderForm(
            request.POST or None,
            store_id=store_id,
            company_id=company_id,
            movement_type=movement.type,
            instance=movement,
        )

    form_kwargs = {"company_id": company_id} if company_id else {}
    formset = MovementDetailEditFormSet(
        request.POST or None, initial=initial_lines, prefix="lines", form_kwargs=form_kwargs
    )
    return form, formset


def movement_edit(request, pk):
    r = _require_auth(request)
    if r:
        return r

    store_id = _get_store_id(request)
    movement = _get_movement_for_store_or_404(pk, store_id)

    if movement.is_locked_for_changes:
        messages.error(request, movement.lock_reason or "Movimiento bloqueado para edición.")
        return redirect("inventory:movement_list")

    company_id = _get_company_id(request)
    form, formset = _movement_forms(request, store_id, movement, company_id=company_id)

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
                "description": cd.get("description", ""),
                "series": cd.get("series", ""),
                "number": cd.get("number", ""),
            }

            if movement.type == MovementType.TRANSFER:
                update_data.update({
                    "warehouse": None,
                    "warehouse_origin": cd["warehouse_origin"],
                    "warehouse_dest": cd["warehouse_dest"],
                    "supplier": None,
                    "customer": None,
                    "document_type": None,
                    "carrier": None,
                })
            elif movement.type == MovementType.ENTRY:
                update_data.update({
                    "warehouse": cd["warehouse"],
                    "warehouse_origin": None,
                    "warehouse_dest": None,
                    "supplier": cd.get("supplier"),
                    "customer": None,
                    "document_type": cd.get("document_type"),
                    "carrier": cd.get("carrier"),
                })
            elif movement.type == MovementType.EXIT:
                update_data.update({
                    "warehouse": cd["warehouse"],
                    "warehouse_origin": None,
                    "warehouse_dest": None,
                    "supplier": None,
                    "customer": cd.get("customer"),
                    "document_type": cd.get("document_type"),
                    "carrier": cd.get("carrier"),
                })
            elif movement.type == MovementType.ADJUSTMENT:
                update_data.update({
                    "warehouse": cd["warehouse"],
                    "warehouse_origin": None,
                    "warehouse_dest": None,
                    "supplier": None,
                    "customer": None,
                    "document_type": None,
                    "carrier": None,
                    "series": "",
                    "number": "",
                })

            try:
                update_movement(movement, lines=lines, updated_by=request.user, **update_data)
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
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
        "units": Unit.objects.all().order_by("code"),
    })


def movement_delete(request, pk):
    r = _require_auth(request)
    if r:
        return r

    store_id = _get_store_id(request)
    movement = _get_movement_for_store_or_404(pk, store_id)

    if request.method == "POST":
        try:
            delete_movement(movement, deleted_by=request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("inventory:movement_list")
        messages.success(request, "Movimiento eliminado correctamente.")
        return redirect("inventory:movement_list")

    return render(request, "inventory/confirm_delete.html", {
        "object": movement,
        "cancel_url": "inventory:movement_list",
    })


def movement_confirm(request, pk):
    r = _require_auth(request)
    if r:
        return r
    if request.method != "POST":
        return redirect("inventory:movement_list")

    store_id = _get_store_id(request)
    movement = _get_movement_for_store_or_404(pk, store_id)

    try:
        confirm_movement(movement, confirmed_by=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Movimiento confirmado correctamente.")

    return redirect("inventory:movement_list")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY
# ══════════════════════════════════════════════════════════════════════════════

def entry_create(request):
    r = _require_auth(request)
    if r:
        return r
    store_id, err = _require_active_store(request)
    if err:
        return err
    company_id = _get_company_id(request)
    form = MovementHeaderForm(
        request.POST or None, store_id=store_id, company_id=company_id, movement_type=MovementType.ENTRY,
        initial={"date": timezone.now().strftime("%Y-%m-%dT%H:%M"), "series": "0000", "number": "0"},
    )
    formset = MovementDetailFormSet(
        request.POST or None, prefix="lines",
        form_kwargs={"company_id": company_id} if company_id else {},
    )

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        lines = _parse_lines(formset)
        if not lines:
            messages.error(request, "Debe agregar al menos un producto.")
        else:
            cd = form.cleaned_data
            warehouse = cd.get("warehouse")
            if not warehouse:
                form.add_error("warehouse", "Debe seleccionar un almacén.")
            else:
                register_entry(
                    store_id=store_id,
                    warehouse_id=str(warehouse.pk),
                    date=cd["date"],
                    lines=lines,
                    created_by=request.user,
                    reason=cd.get("reason", ""),
                    reference_doc=cd.get("reference_doc", ""),
                    description=cd.get("description", ""),
                    series=cd.get("series", ""),
                    number=cd.get("number", ""),
                    supplier_id=cd["supplier"].pk if cd.get("supplier") else None,
                    document_type_id=cd["document_type"].pk if cd.get("document_type") else None,
                )
                messages.success(request, "Entrada registrada correctamente.")
                return redirect("inventory:movement_list")

    return render(request, "inventory/movement_form.html", {
        "form": form,
        "formset": formset,
        "title": "Nueva entrada",
        "movement_type": MovementType.ENTRY,
        "cancel_url": "inventory:movement_list",
        "units": Unit.objects.all().order_by("code"),
    })


# ══════════════════════════════════════════════════════════════════════════════
# EXIT
# ══════════════════════════════════════════════════════════════════════════════

def exit_create(request):
    r = _require_auth(request)
    if r:
        return r
    store_id, err = _require_active_store(request)
    if err:
        return err
    company_id = _get_company_id(request)
    form = MovementHeaderForm(
        request.POST or None, store_id=store_id, company_id=company_id, movement_type=MovementType.EXIT,
        initial={"date": timezone.now().strftime("%Y-%m-%dT%H:%M"), "series": "0000", "number": "0"},
    )
    formset = MovementDetailFormSet(
        request.POST or None, prefix="lines",
        form_kwargs={"company_id": company_id} if company_id else {},
    )

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        lines = _parse_lines(formset)
        if not lines:
            messages.error(request, "Debe agregar al menos un producto.")
        else:
            cd = form.cleaned_data
            warehouse = cd.get("warehouse")
            if not warehouse:
                form.add_error("warehouse", "Debe seleccionar un almacén.")
            else:
                register_exit(
                    store_id=store_id,
                    warehouse_id=str(warehouse.pk),
                    date=cd["date"],
                    lines=lines,
                    created_by=request.user,
                    reason=cd.get("reason", ""),
                    reference_doc=cd.get("reference_doc", ""),
                    description=cd.get("description", ""),
                    series=cd.get("series", ""),
                    number=cd.get("number", ""),
                    customer_id=cd["customer"].pk if cd.get("customer") else None,
                    document_type_id=cd["document_type"].pk if cd.get("document_type") else None,
                )
                messages.success(request, "Salida registrada correctamente.")
                return redirect("inventory:movement_list")

    return render(request, "inventory/movement_form.html", {
        "form": form,
        "formset": formset,
        "title": "Nueva salida",
        "movement_type": MovementType.EXIT,
        "cancel_url": "inventory:movement_list",
        "units": Unit.objects.all().order_by("code"),
    })


# ══════════════════════════════════════════════════════════════════════════════
# TRANSFER
# ══════════════════════════════════════════════════════════════════════════════

def transfer_create(request):
    r = _require_auth(request)
    if r:
        return r
    store_id, err = _require_active_store(request)
    if err:
        return err
    company_id = _get_company_id(request)
    form = MovementTransferForm(
        request.POST or None, store_id=store_id,
        initial={"date": timezone.now().strftime("%Y-%m-%dT%H:%M")},
    )
    formset = MovementDetailFormSet(
        request.POST or None, prefix="lines",
        form_kwargs={"company_id": company_id} if company_id else {},
    )

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        lines = _parse_lines(formset)
        if not lines:
            messages.error(request, "Debe agregar al menos un producto.")
        else:
            cd = form.cleaned_data
            warehouse_origin = cd.get("warehouse_origin")
            warehouse_dest = cd.get("warehouse_dest")
            if not warehouse_origin:
                form.add_error("warehouse_origin", "Debe seleccionar almacén de origen.")
            if not warehouse_dest:
                form.add_error("warehouse_dest", "Debe seleccionar almacén de destino.")
            if warehouse_origin and warehouse_dest:
                register_transfer(
                    store_id=store_id,
                    warehouse_origin_id=str(warehouse_origin.pk),
                    warehouse_dest_id=str(warehouse_dest.pk),
                    date=cd["date"],
                    lines=lines,
                    created_by=request.user,
                    reason=cd.get("reason", ""),
                    reference_doc=cd.get("reference_doc", ""),
                    description=cd.get("description", ""),
                )
                messages.success(request, "Transferencia registrada correctamente.")
                return redirect("inventory:movement_list")

    return render(request, "inventory/movement_form.html", {
        "form": form,
        "formset": formset,
        "title": "Nueva transferencia",
        "movement_type": MovementType.TRANSFER,
        "cancel_url": "inventory:movement_list",
        "units": Unit.objects.all().order_by("code"),
    })


# ══════════════════════════════════════════════════════════════════════════════
# ADJUSTMENT
# ══════════════════════════════════════════════════════════════════════════════

def adjustment_create(request):
    r = _require_auth(request)
    if r:
        return r
    store_id, err = _require_active_store(request)
    if err:
        return err
    company_id = _get_company_id(request)
    form = MovementHeaderForm(
        request.POST or None,
        store_id=store_id,
        company_id=company_id,
        movement_type=MovementType.ADJUSTMENT,
        initial={"date": timezone.now().strftime("%Y-%m-%dT%H:%M"), "reason": "Saldo inicial"},
    )
    formset = MovementDetailFormSet(
        request.POST or None, prefix="lines",
        form_kwargs={"company_id": company_id} if company_id else {},
    )

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        lines = _parse_lines(formset)
        if not lines:
            messages.error(request, "Debe agregar al menos un producto.")
        else:
            cd = form.cleaned_data
            warehouse = cd.get("warehouse")
            if not warehouse:
                form.add_error("warehouse", "Debe seleccionar un almacén.")
            else:
                register_adjustment(
                    store_id=store_id,
                    warehouse_id=str(warehouse.pk),
                    date=cd["date"],
                    lines=lines,
                    created_by=request.user,
                    reason=cd.get("reason", ""),
                    reference_doc=cd.get("reference_doc", ""),
                    description=cd.get("description", ""),
                    series="",
                    number="",
                    supplier_id=None,
                    customer_id=None,
                    document_type_id=None,
                    carrier_id=None,
                )
                messages.success(request, "Ajuste registrado correctamente.")
                return redirect("inventory:movement_list")

    return render(request, "inventory/movement_form.html", {
        "form": form,
        "formset": formset,
        "title": "Nuevo ajuste",
        "movement_type": MovementType.ADJUSTMENT,
        "cancel_url": "inventory:movement_list",
        "units": Unit.objects.all().order_by("code"),
    })


# ══════════════════════════════════════════════════════════════════════════════
# COPY
# ══════════════════════════════════════════════════════════════════════════════

def movement_copy(request, pk):
    r = _require_auth(request)
    if r:
        return r

    store_id, err = _require_active_store(request)
    if err:
        return err
    company_id = _get_company_id(request)

    source = get_object_or_404(
        Movement.objects.prefetch_related("details__product__unit"),
        pk=pk,
        store_id=store_id,
    )

    initial_header = {
        "date": timezone.now().strftime("%Y-%m-%dT%H:%M"),
        "reason": source.reason,
        "description": source.description,
        "reference_doc": "",
        "series": source.series or "0000",
        "number": source.number or "0",
    }

    if source.type == MovementType.TRANSFER:
        initial_header.update({
            "warehouse_origin": source.warehouse_origin_id,
            "warehouse_dest": source.warehouse_dest_id,
        })
    elif source.type == MovementType.ADJUSTMENT:
        initial_header.update({
            "warehouse": source.warehouse_id,
            "series": "",
            "number": "",
        })
    else:
        initial_header.update({
            "warehouse": source.warehouse_id,
            "supplier": source.supplier_id,
            "customer": source.customer_id,
            "document_type": source.document_type_id,
            "carrier": source.carrier_id,
        })

    initial_lines = [
        {
            "product": d.product_id,
            "product_name": d.product.name,
            "product_unit": d.product.unit.code if d.product.unit else "",
            "quantity": (
                d.physical_quantity
                if source.type == MovementType.ADJUSTMENT and d.physical_quantity is not None
                else d.quantity
            ),
            "unit_price": d.unit_price,
        }
        for d in source.details.all()
    ]

    if source.type == MovementType.TRANSFER:
        form = MovementTransferForm(request.POST or None, store_id=store_id, initial=initial_header)
    else:
        form = MovementHeaderForm(
            request.POST or None,
            store_id=store_id,
            company_id=company_id,
            movement_type=source.type,
            initial=initial_header,
        )

    form_kwargs = {"company_id": company_id} if company_id else {}
    formset = MovementDetailFormSet(
        request.POST or None,
        initial=initial_lines,
        prefix="lines",
        form_kwargs=form_kwargs,
    )

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        lines = _parse_lines(formset)
        if not lines:
            messages.error(request, "Debe agregar al menos un producto.")
        else:
            cd = form.cleaned_data
            try:
                if source.type == MovementType.ENTRY:
                    warehouse = cd.get("warehouse")
                    if not warehouse:
                        form.add_error("warehouse", "Debe seleccionar un almacén.")
                    else:
                        register_entry(
                            store_id=store_id,
                            warehouse_id=str(warehouse.pk),
                            date=cd["date"],
                            lines=lines,
                            created_by=request.user,
                            reason=cd.get("reason", ""),
                            reference_doc=cd.get("reference_doc", ""),
                            description=cd.get("description", ""),
                            series=cd.get("series", ""),
                            number=cd.get("number", ""),
                            supplier_id=cd["supplier"].pk if cd.get("supplier") else None,
                            document_type_id=cd["document_type"].pk if cd.get("document_type") else None,
                        )
                        messages.success(request, "Entrada copiada y registrada correctamente.")
                        return redirect("inventory:movement_list")
                elif source.type == MovementType.EXIT:
                    warehouse = cd.get("warehouse")
                    if not warehouse:
                        form.add_error("warehouse", "Debe seleccionar un almacén.")
                    else:
                        register_exit(
                            store_id=store_id,
                            warehouse_id=str(warehouse.pk),
                            date=cd["date"],
                            lines=lines,
                            created_by=request.user,
                            reason=cd.get("reason", ""),
                            reference_doc=cd.get("reference_doc", ""),
                            description=cd.get("description", ""),
                            series=cd.get("series", ""),
                            number=cd.get("number", ""),
                            customer_id=cd["customer"].pk if cd.get("customer") else None,
                            document_type_id=cd["document_type"].pk if cd.get("document_type") else None,
                        )
                        messages.success(request, "Salida copiada y registrada correctamente.")
                        return redirect("inventory:movement_list")
                elif source.type == MovementType.TRANSFER:
                    warehouse_origin = cd.get("warehouse_origin")
                    warehouse_dest = cd.get("warehouse_dest")
                    if not warehouse_origin:
                        form.add_error("warehouse_origin", "Debe seleccionar almacén de origen.")
                    if not warehouse_dest:
                        form.add_error("warehouse_dest", "Debe seleccionar almacén de destino.")
                    if warehouse_origin and warehouse_dest:
                        register_transfer(
                            store_id=store_id,
                            warehouse_origin_id=str(warehouse_origin.pk),
                            warehouse_dest_id=str(warehouse_dest.pk),
                            date=cd["date"],
                            lines=lines,
                            created_by=request.user,
                            reason=cd.get("reason", ""),
                            reference_doc=cd.get("reference_doc", ""),
                            description=cd.get("description", ""),
                        )
                        messages.success(request, "Transferencia copiada y registrada correctamente.")
                        return redirect("inventory:movement_list")
                elif source.type == MovementType.ADJUSTMENT:
                    warehouse = cd.get("warehouse")
                    if not warehouse:
                        form.add_error("warehouse", "Debe seleccionar un almacén.")
                    else:
                        register_adjustment(
                            store_id=store_id,
                            warehouse_id=str(warehouse.pk),
                            date=cd["date"],
                            lines=lines,
                            created_by=request.user,
                            reason=cd.get("reason", ""),
                            reference_doc=cd.get("reference_doc", ""),
                            description=cd.get("description", ""),
                            series="",
                            number="",
                            supplier_id=None,
                            customer_id=None,
                            document_type_id=None,
                            carrier_id=None,
                        )
                        messages.success(request, "Ajuste copiado y registrado correctamente.")
                        return redirect("inventory:movement_list")
            except ValueError as exc:
                messages.error(request, str(exc))

    type_labels = {
        MovementType.ENTRY: "entrada",
        MovementType.EXIT: "salida",
        MovementType.TRANSFER: "transferencia",
        MovementType.ADJUSTMENT: "ajuste",
    }
    return render(request, "inventory/movement_form.html", {
        "form": form,
        "formset": formset,
        "title": f"Copiar {type_labels.get(source.type, 'movimiento')}",
        "movement_type": source.type,
        "cancel_url": "inventory:movement_list",
        "units": Unit.objects.all().order_by("code"),
    })
