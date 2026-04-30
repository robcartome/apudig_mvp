"""
partners/services.py — Lógica de negocio de clientes y proveedores.
"""
from django.db import transaction

from .models import CoreCustomer, SalesCustomerProfile, Supplier


@transaction.atomic
def create_customer(document_type: str, document_number: str, legal_name: str, **kwargs) -> CoreCustomer:
    """
    Crea un cliente canónico. Si ya existe por documento, lanza IntegrityError.
    """
    return CoreCustomer.objects.create(
        document_type=document_type,
        document_number=document_number,
        legal_name=legal_name,
        **kwargs,
    )


@transaction.atomic
def update_customer(customer: CoreCustomer, **fields) -> CoreCustomer:
    for attr, value in fields.items():
        setattr(customer, attr, value)
    customer.save()
    return customer


@transaction.atomic
def create_supplier(name: str, document_number: str, **kwargs) -> Supplier:
    return Supplier.objects.create(
        name=name, document_number=document_number, **kwargs
    )
