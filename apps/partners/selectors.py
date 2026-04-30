"""
partners/selectors.py — Consultas de lectura de clientes y proveedores.
"""
from .models import CoreCustomer, Supplier


def search_customers(query: str = "", active_only: bool = True):
    """
    Busca clientes por nombre legal, nombre comercial o número de documento.
    """
    qs = CoreCustomer.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    if query:
        qs = qs.filter(
            legal_name__icontains=query
        ) | qs.filter(
            trade_name__icontains=query
        ) | qs.filter(
            document_number__icontains=query
        )
    return qs.order_by("legal_name")


def get_customer_by_document(document_type: str, document_number: str):
    return CoreCustomer.objects.filter(
        document_type=document_type,
        document_number=document_number,
    ).first()


def search_suppliers(query: str = "", active_only: bool = True):
    qs = Supplier.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    if query:
        qs = qs.filter(name__icontains=query) | qs.filter(document_number__icontains=query)
    return qs.order_by("name")
