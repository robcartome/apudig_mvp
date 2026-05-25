"""
partners/selectors.py — Consultas de lectura de clientes, proveedores y transportistas.
"""
from apps.core.managers import filter_by_company

from .models import Carrier, Customer, Supplier


def get_customers(company_id=None, active_only: bool = True):
    qs = Customer.objects.for_company(company_id) if company_id else Customer.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    return qs.order_by("legal_name")


def search_customers(query: str = "", company_id=None, active_only: bool = True):
    qs = Customer.objects.for_company(company_id) if company_id else Customer.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    if query:
        qs = (
            qs.filter(legal_name__icontains=query)
            | qs.filter(trade_name__icontains=query)
            | qs.filter(document_number__icontains=query)
        )
    return qs.order_by("legal_name")


def get_customer_by_document(document_type: str, document_number: str, company_id=None):
    qs = Customer.objects.filter(
        document_type=document_type,
        document_number=document_number,
    )
    if company_id:
        qs = qs.filter(company_id=company_id)
    return qs.first()


def get_suppliers(company_id=None, active_only: bool = True):
    qs = Supplier.objects.for_company(company_id) if company_id else Supplier.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    return qs.order_by("name")


def search_suppliers(query: str = "", company_id=None, active_only: bool = True):
    qs = Supplier.objects.for_company(company_id) if company_id else Supplier.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    if query:
        qs = qs.filter(name__icontains=query) | qs.filter(document_number__icontains=query)
    return qs.order_by("name")


def get_carriers(company_id=None, active_only: bool = True):
    qs = Carrier.objects.for_company(company_id) if company_id else Carrier.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    return qs.order_by("business_name")


def search_carriers(query: str = "", company_id=None, active_only: bool = True):
    qs = Carrier.objects.for_company(company_id) if company_id else Carrier.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    if query:
        qs = (
            qs.filter(business_name__icontains=query)
            | qs.filter(document_number__icontains=query)
            | qs.filter(driver_name__icontains=query)
        )
    return qs.order_by("business_name")
