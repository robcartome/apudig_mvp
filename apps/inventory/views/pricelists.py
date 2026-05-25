"""
inventory/views/pricelists.py — CRUD de Listas de Precio y asignación de precios a productos.

Rutas:
  pricelist_list      GET      /inventario/listas-precio/
  pricelist_create    GET+POST /inventario/listas-precio/nueva/
  pricelist_detail    GET      /inventario/listas-precio/<uuid:pk>/
  pricelist_update    GET+POST /inventario/listas-precio/<uuid:pk>/editar/
  pricelist_toggle    POST     /inventario/listas-precio/<uuid:pk>/toggle/
  pricelist_set_price POST     /inventario/listas-precio/<uuid:pk>/precio/
  pricelist_del_price POST     /inventario/listas-precio/<uuid:pk>/precio/eliminar/
"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.companies.models import Company

from ..forms import PriceListForm, ProductPriceFormSet
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
