"""
partners/views/partners.py — CRUDs de clientes, proveedores y transportistas.
"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from apps.companies.models import Company

from ..forms import CarrierForm, CustomerContactForm, CustomerForm, CustomerProfileForm, SupplierForm
from ..models import Carrier, CoreCustomer, SalesCustomerContact, SalesCustomerProfile, Supplier
from ..selectors import (
    get_carriers,
    get_customers,
    get_suppliers,
    search_carriers,
    search_customers,
    search_suppliers,
)


def _paginate(request, qs, per_page: int = 25):
    paginator = Paginator(qs, per_page)
    return paginator.get_page(request.GET.get("page", 1))


def _require_auth(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return None


def _require_company(request):
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


# ══════════════════════════════════════════════════════════════════════════════
# CUSTOMERS
# ══════════════════════════════════════════════════════════════════════════════

def customer_list(request):
    r = _require_auth(request)
    if r:
        return r
    company, err = _require_company(request)
    if err:
        return err
    query = request.GET.get("q", "")
    show_inactive = request.GET.get("inactive", "") == "1"
    qs = search_customers(query, company_id=company.pk, active_only=not show_inactive)
    page_obj = _paginate(request, qs)
    return render(request, "partners/customer_list.html", {
        "page_obj": page_obj, "query": query, "show_inactive": show_inactive,
    })


def customer_create(request):
    r = _require_auth(request)
    if r:
        return r
    company, err = _require_company(request)
    if err:
        return err
    form = CustomerForm(request.POST or None, company=company)
    profile_form = CustomerProfileForm(request.POST or None, company_id=company.pk)
    if request.method == "POST" and form.is_valid() and profile_form.is_valid():
        try:
            customer = form.save()
            profile = profile_form.save(commit=False)
            profile.core_customer = customer
            profile.save()
            messages.success(request, f"Cliente «{customer.legal_name}» creado correctamente.")
            return redirect("partners:customer_detail", pk=customer.pk)
        except IntegrityError:
            form.add_error("document_number", "Ya existe un cliente con ese tipo y número de documento.")
    return render(request, "partners/customer_form.html", {
        "form": form,
        "profile_form": profile_form,
        "title": "Nuevo cliente",
        "cancel_url": "partners:customer_list",
    })


def customer_detail(request, pk):
    r = _require_auth(request)
    if r:
        return r
    company, err = _require_company(request)
    if err:
        return err
    customer = get_object_or_404(CoreCustomer, pk=pk, company=company)
    profile = getattr(customer, "sales_profile", None)
    contacts = SalesCustomerContact.objects.for_company(company.pk).filter(customer=customer)
    return render(request, "partners/customer_detail.html", {
        "customer": customer,
        "profile": profile,
        "contacts": contacts,
    })


def customer_update(request, pk):
    r = _require_auth(request)
    if r:
        return r
    company, err = _require_company(request)
    if err:
        return err
    customer = get_object_or_404(CoreCustomer, pk=pk, company=company)
    profile, _ = SalesCustomerProfile.objects.get_or_create(core_customer=customer)
    form = CustomerForm(request.POST or None, instance=customer, company=company)
    profile_form = CustomerProfileForm(request.POST or None, instance=profile, company_id=company.pk)
    if request.method == "POST" and form.is_valid() and profile_form.is_valid():
        try:
            form.save()
            profile_form.save()
            messages.success(request, "Cliente actualizado correctamente.")
            return redirect("partners:customer_detail", pk=pk)
        except IntegrityError:
            form.add_error("document_number", "Ya existe un cliente con ese tipo y número de documento.")
    return render(request, "partners/customer_form.html", {
        "form": form,
        "profile_form": profile_form,
        "title": "Editar cliente",
        "object": customer,
        "cancel_url": "partners:customer_detail",
        "cancel_pk": pk,
    })


def customer_delete(request, pk):
    r = _require_auth(request)
    if r:
        return r
    company, err = _require_company(request)
    if err:
        return err
    customer = get_object_or_404(CoreCustomer, pk=pk, company=company)
    if request.method == "POST":
        try:
            name = customer.legal_name
            customer.delete()
            messages.success(request, f"Cliente «{name}» eliminado.")
        except Exception:
            messages.error(request, "No se puede eliminar el cliente porque tiene registros asociados.")
        return redirect("partners:customer_list")
    return render(request, "partners/confirm_delete.html", {
        "object_name": customer.legal_name,
        "cancel_url": "partners:customer_detail",
        "cancel_pk": pk,
    })


# ── Contacts ──────────────────────────────────────────────────────────────────

def contact_create(request, customer_pk):
    r = _require_auth(request)
    if r:
        return r
    company, err = _require_company(request)
    if err:
        return err
    customer = get_object_or_404(CoreCustomer, pk=customer_pk, company=company)
    form = CustomerContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        contact = form.save(commit=False)
        contact.customer = customer
        contact.save()
        messages.success(request, "Contacto agregado.")
        return redirect("partners:customer_detail", pk=customer_pk)
    return render(request, "partners/contact_form.html", {
        "form": form,
        "customer": customer,
        "title": "Nuevo contacto",
    })


def contact_delete(request, pk):
    r = _require_auth(request)
    if r:
        return r
    company, err = _require_company(request)
    if err:
        return err
    contact = get_object_or_404(SalesCustomerContact.objects.for_company(company.pk), pk=pk)
    customer_pk = contact.customer_id
    if request.method == "POST":
        contact.delete()
        messages.success(request, "Contacto eliminado.")
    return redirect("partners:customer_detail", pk=customer_pk)


# ══════════════════════════════════════════════════════════════════════════════
# SUPPLIERS
# ══════════════════════════════════════════════════════════════════════════════

def supplier_list(request):
    r = _require_auth(request)
    if r:
        return r
    company, err = _require_company(request)
    if err:
        return err
    query = request.GET.get("q", "")
    show_inactive = request.GET.get("inactive", "") == "1"
    qs = search_suppliers(query, company_id=company.pk, active_only=not show_inactive)
    page_obj = _paginate(request, qs)
    return render(request, "partners/supplier_list.html", {
        "page_obj": page_obj, "query": query, "show_inactive": show_inactive,
    })


def supplier_create(request):
    r = _require_auth(request)
    if r:
        return r
    company, err = _require_company(request)
    if err:
        return err
    form = SupplierForm(request.POST or None, company=company)
    if request.method == "POST" and form.is_valid():
        try:
            supplier = form.save()
            messages.success(request, f"Proveedor «{supplier.name}» creado correctamente.")
            return redirect("partners:supplier_list")
        except IntegrityError:
            form.add_error("document_number", "Ya existe un proveedor con ese número de documento.")
    return render(request, "partners/supplier_form.html", {
        "form": form, "title": "Nuevo proveedor", "cancel_url": "partners:supplier_list",
    })


def supplier_update(request, pk):
    r = _require_auth(request)
    if r:
        return r
    company, err = _require_company(request)
    if err:
        return err
    supplier = get_object_or_404(Supplier, pk=pk, company=company)
    form = SupplierForm(request.POST or None, instance=supplier, company=company)
    if request.method == "POST" and form.is_valid():
        try:
            form.save()
            messages.success(request, "Proveedor actualizado correctamente.")
            return redirect("partners:supplier_list")
        except IntegrityError:
            form.add_error("document_number", "Ya existe un proveedor con ese número de documento.")
    return render(request, "partners/supplier_form.html", {
        "form": form, "title": "Editar proveedor", "object": supplier, "cancel_url": "partners:supplier_list",
    })


def supplier_delete(request, pk):
    r = _require_auth(request)
    if r:
        return r
    company, err = _require_company(request)
    if err:
        return err
    supplier = get_object_or_404(Supplier, pk=pk, company=company)
    if request.method == "POST":
        try:
            name = supplier.name
            supplier.delete()
            messages.success(request, f"Proveedor «{name}» eliminado.")
        except Exception:
            messages.error(request, "No se puede eliminar el proveedor porque tiene registros asociados.")
        return redirect("partners:supplier_list")
    return render(request, "partners/confirm_delete.html", {
        "object_name": supplier.name,
        "cancel_url": "partners:supplier_list",
    })


# ══════════════════════════════════════════════════════════════════════════════
# CARRIERS
# ══════════════════════════════════════════════════════════════════════════════

def carrier_list(request):
    r = _require_auth(request)
    if r:
        return r
    company, err = _require_company(request)
    if err:
        return err
    query = request.GET.get("q", "")
    show_inactive = request.GET.get("inactive", "") == "1"
    qs = search_carriers(query, company_id=company.pk, active_only=not show_inactive)
    page_obj = _paginate(request, qs)
    return render(request, "partners/carrier_list.html", {
        "page_obj": page_obj, "query": query, "show_inactive": show_inactive,
    })


def carrier_create(request):
    r = _require_auth(request)
    if r:
        return r
    company, err = _require_company(request)
    if err:
        return err
    form = CarrierForm(request.POST or None, company=company)
    if request.method == "POST" and form.is_valid():
        carrier = form.save()
        messages.success(request, f"Transportista «{carrier.business_name}» creado correctamente.")
        return redirect("partners:carrier_list")
    return render(request, "partners/carrier_form.html", {
        "form": form, "title": "Nuevo transportista", "cancel_url": "partners:carrier_list",
    })


def carrier_update(request, pk):
    r = _require_auth(request)
    if r:
        return r
    company, err = _require_company(request)
    if err:
        return err
    carrier = get_object_or_404(Carrier, pk=pk, company=company)
    form = CarrierForm(request.POST or None, instance=carrier, company=company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Transportista actualizado correctamente.")
        return redirect("partners:carrier_list")
    return render(request, "partners/carrier_form.html", {
        "form": form, "title": "Editar transportista", "object": carrier, "cancel_url": "partners:carrier_list",
    })


def carrier_delete(request, pk):
    r = _require_auth(request)
    if r:
        return r
    company, err = _require_company(request)
    if err:
        return err
    carrier = get_object_or_404(Carrier, pk=pk, company=company)
    if request.method == "POST":
        try:
            name = carrier.business_name
            carrier.delete()
            messages.success(request, f"Transportista «{name}» eliminado.")
        except Exception:
            messages.error(request, "No se puede eliminar el transportista porque tiene registros asociados.")
        return redirect("partners:carrier_list")
    return render(request, "partners/confirm_delete.html", {
        "object_name": carrier.business_name,
        "cancel_url": "partners:carrier_list",
    })
