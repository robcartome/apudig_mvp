"""
partners/services.py — Lógica de negocio de clientes y proveedores.
"""
from django.db import transaction

from .models import Customer, SalesCustomerProfile, Supplier


@transaction.atomic
def create_customer(document_type: str, document_number: str, legal_name: str, company_id=None, **kwargs) -> Customer:
    """
    Crea un cliente canónico. Si ya existe por documento, lanza IntegrityError.
    """
    return Customer.objects.create(
        company_id=company_id,
        document_type=document_type,
        document_number=document_number,
        legal_name=legal_name,
        **kwargs,
    )


@transaction.atomic
def update_customer(customer: Customer, **fields) -> Customer:
    for attr, value in fields.items():
        setattr(customer, attr, value)
    customer.save()
    return customer


@transaction.atomic
def create_supplier(name: str, document_number: str, company_id=None, **kwargs) -> Supplier:
    return Supplier.objects.create(
        name=name, document_number=document_number, company_id=company_id, **kwargs
    )
