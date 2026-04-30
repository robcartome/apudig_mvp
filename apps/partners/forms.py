"""
partners/forms.py — Formularios de clientes y proveedores.
"""
from django import forms

from .models import CoreCustomer, SalesCustomerContact, SalesCustomerProfile, Supplier


class CustomerForm(forms.ModelForm):
    class Meta:
        model = CoreCustomer
        fields = (
            "document_type",
            "document_number",
            "legal_name",
            "trade_name",
            "address",
            "phone",
            "email",
            "active",
        )


class CustomerProfileForm(forms.ModelForm):
    class Meta:
        model = SalesCustomerProfile
        fields = ("taxpayer_status", "payment_term_days", "price_list", "notes", "active")


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ("name", "document_number", "address", "phone", "email", "contact_name", "active")
