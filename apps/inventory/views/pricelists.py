"""
inventory/views/pricelists.py — CRUD de Listas de Precio y asignación de precios a productos.

Rutas:
  pricelist_list              GET      /inventario/listas-precio/
  pricelist_create            GET+POST /inventario/listas-precio/nueva/
  pricelist_detail            GET      /inventario/listas-precio/<uuid:pk>/
  pricelist_update            GET+POST /inventario/listas-precio/<uuid:pk>/editar/
  pricelist_toggle            POST     /inventario/listas-precio/<uuid:pk>/toggle/
  pricelist_del_price         POST     /inventario/listas-precio/<uuid:pk>/precio/eliminar/
  pricelist_bulk_template     GET      /inventario/listas-precio/import/template/
  pricelist_bulk_import       GET+POST /inventario/listas-precio/import/
  pricelist_bulk_template_pl  GET      /inventario/listas-precio/<uuid:pk>/import/template/
  pricelist_bulk_import_pl    GET+POST /inventario/listas-precio/<uuid:pk>/import/
"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify

from apps.companies.models import Company

from ..forms import BulkImportForm, PriceListForm, ProductPriceFormSet
from ..models import PriceList, Product, ProductPrice
from ..selectors import get_pricelist_detail, get_price_lists, search_price_lists
from ..services import (
    create_price_list,
    delete_product_price,
    set_product_price,
    toggle_price_list,
)


def _require_auth(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return None


def _get_active_company(request):
    """Returns (Company, None) or (None, redirect_response)."""
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


# ── Listado ───────────────────────────────────────────────────────────────────

def pricelist_list(request):
    r = _require_auth(request)
    if r:
        return r

    company, err = _get_active_company(request)
    if err:
        return err

    q = request.GET.get("q", "").strip()
    qs = search_price_lists(q, company_id=company.pk) if q else get_price_lists(company_id=company.pk)
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "inventory/pricelist_list.html", {
        "page_obj": page_obj,
        "q": q,
    })


# ── Crear ─────────────────────────────────────────────────────────────────────

def pricelist_create(request):
    r = _require_auth(request)
    if r:
        return r

    company, err = _get_active_company(request)
    if err:
        return err

    if request.method == "POST":
        form = PriceListForm(request.POST)
        if form.is_valid():
            pl = create_price_list(
                name=form.cleaned_data["name"],
                description=form.cleaned_data.get("description", ""),
                active=form.cleaned_data.get("active", True),
                company_id=company.pk,
            )
            messages.success(request, f"Lista «{pl.name}» creada.")
            return redirect("inventory:pricelist_detail", pk=pl.pk)
    else:
        form = PriceListForm()

    return render(request, "inventory/pricelist_form.html", {
        "form": form,
        "title": "Nueva lista de precios",
    })


# ── Detalle ───────────────────────────────────────────────────────────────────

def pricelist_detail(request, pk):
    r = _require_auth(request)
    if r:
        return r

    company, err = _get_active_company(request)
    if err:
        return err

    try:
        pl = get_pricelist_detail(pk)
    except PriceList.DoesNotExist:
        raise Http404
    # Guard: only own company's lists
    if pl.company_id and str(pl.company_id) != str(company.pk):
        raise Http404

    # Formset para agregar/editar precios en bulk
    if request.method == "POST":
        formset = ProductPriceFormSet(request.POST, prefix="prices", form_kwargs={"company_id": company.pk})
        if formset.is_valid():
            saved = 0
            for f in formset:
                cd = f.cleaned_data
                if not cd or cd.get("DELETE"):
                    continue
                set_product_price(
                    pricelist_id=pl.pk,
                    product_id=cd["product"].pk,
                    amount=cd["amount"],
                    currency=cd.get("currency", "PEN"),
                )
                saved += 1
            messages.success(request, f"{saved} precio(s) actualizados.")
            return redirect("inventory:pricelist_detail", pk=pk)
    else:
        formset = ProductPriceFormSet(prefix="prices", form_kwargs={"company_id": company.pk})

    return render(request, "inventory/pricelist_detail.html", {
        "pl": pl,
        "formset": formset,
    })


# ── Editar ────────────────────────────────────────────────────────────────────

def pricelist_update(request, pk):
    r = _require_auth(request)
    if r:
        return r

    company, err = _get_active_company(request)
    if err:
        return err

    pl = get_object_or_404(PriceList, pk=pk, company=company)

    if request.method == "POST":
        form = PriceListForm(request.POST, instance=pl)
        if form.is_valid():
            form.save()
            messages.success(request, "Lista actualizada.")
            return redirect("inventory:pricelist_detail", pk=pl.pk)
    else:
        form = PriceListForm(instance=pl)

    return render(request, "inventory/pricelist_form.html", {
        "form": form,
        "title": f"Editar «{pl.name}»",
        "pl": pl,
    })


# ── Toggle activo/inactivo ────────────────────────────────────────────────────

def pricelist_toggle(request, pk):
    r = _require_auth(request)
    if r:
        return r

    if request.method != "POST":
        return redirect("inventory:pricelist_detail", pk=pk)

    pl = get_object_or_404(PriceList, pk=pk)
    toggle_price_list(pl)
    estado = "activada" if pl.active else "desactivada"
    messages.success(request, f"Lista «{pl.name}» {estado}.")
    return redirect("inventory:pricelist_list")


# ── Eliminar precio individual ────────────────────────────────────────────────

def pricelist_del_price(request, pk):
    """Elimina un ProductPrice de la lista vía POST con product_id."""
    r = _require_auth(request)
    if r:
        return r

    if request.method != "POST":
        return redirect("inventory:pricelist_detail", pk=pk)

    product_id = request.POST.get("product_id")
    if product_id:
        delete_product_price(pricelist_id=pk, product_id=product_id)
        messages.success(request, "Precio eliminado.")

    return redirect("inventory:pricelist_detail", pk=pk)


# ── Bulk import helpers ───────────────────────────────────────────────────────

def _pricelist_bulk_template(request, pricelist=None):
    """Download Excel price template (global or per-list)."""
    r = _require_auth(request)
    if r:
        return r

    company, err = _get_active_company(request)
    if err:
        return err

    from ..importers import build_pricelist_template_workbook

    try:
        data = build_pricelist_template_workbook(company=company, pricelist=pricelist)
    except ValueError as exc:
        messages.error(request, str(exc))
        if pricelist:
            return redirect("inventory:pricelist_detail", pk=pricelist.pk)
        return redirect("inventory:pricelist_list")

    list_name = pricelist.name if pricelist else "todas_listas"
    safe_name = slugify(list_name) or "precios"
    filename = f"plantilla_precios_{safe_name}.xlsx"
    response = HttpResponse(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _pricelist_bulk_import(request, pricelist=None):
    """Upload and process a price Excel file (global or per-list)."""
    r = _require_auth(request)
    if r:
        return r

    company, err = _get_active_company(request)
    if err:
        return err

    from ..importers import import_pricelist_excel

    form = BulkImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["file"]
        try:
            result = import_pricelist_excel(
                file_obj=upload,
                filename=upload.name,
                company=company,
                pricelist=pricelist,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        except Exception as exc:
            messages.error(request, f"Error al procesar archivo: {exc}")
        else:
            if result.errors:
                for err_line in result.errors[:20]:
                    messages.warning(request, err_line)
                if len(result.errors) > 20:
                    messages.warning(request, f"... y {len(result.errors) - 20} errores adicionales.")
                messages.error(
                    request,
                    f"Importación con errores — filas procesadas: {result.updated}, "
                    f"errores: {len(result.errors)}.",
                )
            else:
                messages.success(
                    request,
                    f"Precios actualizados correctamente. "
                    f"Filas procesadas: {result.updated} de {result.total_rows}.",
                )
        if pricelist:
            return redirect("inventory:pricelist_detail", pk=pricelist.pk)
        return redirect("inventory:pricelist_list")

    # Determine download URL for template button
    if pricelist:
        template_url = f"inventory:pricelist_bulk_template_pl"
        template_url_kwargs = {"pk": pricelist.pk}
    else:
        template_url = "inventory:pricelist_bulk_template"
        template_url_kwargs = {}

    return render(request, "inventory/pricelist_bulk_import.html", {
        "form": form,
        "pl": pricelist,
        "template_url": template_url,
        "template_url_kwargs": template_url_kwargs,
    })


# ── Public wrappers ───────────────────────────────────────────────────────────

def pricelist_bulk_template(request):
    """GET — Download global price template (all lists × all products)."""
    return _pricelist_bulk_template(request, pricelist=None)


def pricelist_bulk_import(request):
    """GET+POST — Bulk price import (all lists)."""
    return _pricelist_bulk_import(request, pricelist=None)


def pricelist_bulk_template_pl(request, pk):
    """GET — Download per-list price template."""
    r = _require_auth(request)
    if r:
        return r
    company, err = _get_active_company(request)
    if err:
        return err
    pl = get_object_or_404(PriceList, pk=pk, company=company)
    return _pricelist_bulk_template(request, pricelist=pl)


def pricelist_bulk_import_pl(request, pk):
    """GET+POST — Bulk price import for a specific list."""
    r = _require_auth(request)
    if r:
        return r
    company, err = _get_active_company(request)
    if err:
        return err
    pl = get_object_or_404(PriceList, pk=pk, company=company)
    return _pricelist_bulk_import(request, pricelist=pl)


# ── Reporte consolidado de precios ────────────────────────────────────────────

def price_report(request):
    """Consolidated price report: all products × all active price lists.

    ?q        — search by SKU, name or barcode
    ?format   — xlsx | print  (default: HTML)
    """
    r = _require_auth(request)
    if r:
        return r

    company, err = _get_active_company(request)
    if err:
        return err

    from ..selectors import get_price_consolidate
    from ..importers import build_price_report_workbook

    q = request.GET.get("q", "").strip()
    fmt = request.GET.get("format", "").strip().lower()

    price_lists, rows = get_price_consolidate(company.pk, query=q)

    # Parse selected columns for Excel export (?cols=compra,venta,<uuid>,...)
    # All columns shown by default; cols param restricts what goes into Excel.
    cols_param = request.GET.get("cols", "").strip()
    if cols_param:
        selected_cols = set(cols_param.split(","))
    else:
        selected_cols = {"compra", "venta"} | {str(pl.pk) for pl in price_lists}

    if fmt == "xlsx":
        # Filter price_lists and rows to match selected_cols
        show_compra = "compra" in selected_cols
        show_venta = "venta" in selected_cols
        xl_lists = [pl for pl in price_lists if str(pl.pk) in selected_cols]

        # Rebuild rows with only selected pl_amounts
        xl_rows = []
        for row in rows:
            xl_rows.append({
                "sku": row["sku"],
                "name": row["name"],
                "price_purchase": row["price_purchase"] if show_compra else None,
                "price_sale": row["price_sale"] if show_venta else None,
                "prices": {str(pl.pk): row["prices"].get(str(pl.pk)) for pl in xl_lists},
                "_show_compra": show_compra,
                "_show_venta": show_venta,
            })
        try:
            data = build_price_report_workbook(
                price_lists=xl_lists,
                rows=xl_rows,
                show_compra=show_compra,
                show_venta=show_venta,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("inventory:price_report")
        response = HttpResponse(
            data,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        suffix = f"_{slugify(q)}" if q else ""
        response["Content-Disposition"] = f'attachment; filename="consolidado_precios{suffix}.xlsx"'
        return response

    # Transform rows: add pl_amounts list aligned to price_lists order
    for row in rows:
        row["pl_amounts"] = [row["prices"].get(str(pl.pk)) for pl in price_lists]

    # Paginate for screen
    paginator = Paginator(rows, 50)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    return render(request, "inventory/pricelist_report.html", {
        "price_lists": price_lists,
        "page_obj": page_obj,
        "rows": page_obj.object_list,
        "q": q,
        "total": len(rows),
        "selected_cols": selected_cols,
    })
