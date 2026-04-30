"""
partners/selectors.py — Consultas de lectura de clientes, proveedores y transportistas.
"""
from .models import Carrier, CoreCustomer, Supplier


def get_customers(active_only: bool = True):
    qs = CoreCustomer.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    return qs.order_by("legal_name")


def search_customers(query: str = "", active_only: bool = True):
    qs = CoreCustomer.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    if query:
        qs = (
            qs.filter(legal_name__icontains=query)
            | qs.filter(trade_name__icontains=query)
            | qs.filter(document_number__icontains=query)
        )
    return qs.order_by("legal_name")


def get_customer_by_document(document_type: str, document_number: str):
    return CoreCustomer.objects.filter(
        document_type=document_type,
        document_number=document_number,
    ).first()


def get_suppliers(active_only: bool = True):
    qs = Supplier.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    return qs.order_by("name")


def search_suppliers(query: str = "", active_only: bool = True):
    qs = Supplier.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    if query:
        qs = qs.filter(name__icontains=query) | qs.filter(document_number__icontains=query)
    return qs.order_by("name")


def get_carriers(active_only: bool = True):
    qs = Carrier.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    return qs.order_by("business_name")


def search_carriers(query: str = "", active_only: bool = True):
    qs = Carrier.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    if query:
        qs = (
            qs.filter(business_name__icontains=query)
            | qs.filter(document_number__icontains=query)
            | qs.filter(driver_name__icontains=query)
        )
    return qs.order_by("business_name")
