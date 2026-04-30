"""
partners/forms.py — Formularios de clientes, proveedores y transportistas.
"""
from django import forms

from .models import Carrier, CoreCustomer, SalesCustomerContact, SalesCustomerProfile, Supplier

_text = {"class": "form-control"}
_select = {"class": "form-select"}
_check = {"class": "form-check-input"}
_textarea = {"class": "form-control", "rows": 3}


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
        widgets = {
            "document_type": forms.Select(attrs=_select),
            "document_number": forms.TextInput(attrs=_text),
            "legal_name": forms.TextInput(attrs=_text),
            "trade_name": forms.TextInput(attrs=_text),
            "address": forms.TextInput(attrs=_text),
            "phone": forms.TextInput(attrs=_text),
            "email": forms.EmailInput(attrs=_text),
            "active": forms.CheckboxInput(attrs=_check),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["document_type"].widget = forms.Select(
            attrs=_select,
            choices=[
                ("", "— Seleccione —"),
                ("1", "DNI"),
                ("6", "RUC"),
                ("4", "Carné de extranjería"),
                ("7", "Pasaporte"),
                ("0", "Otro"),
            ],
        )
        self.fields["trade_name"].required = False
        self.fields["address"].required = False
        self.fields["phone"].required = False
        self.fields["email"].required = False


class CustomerProfileForm(forms.ModelForm):
    class Meta:
        model = SalesCustomerProfile
        fields = ("taxpayer_status", "taxpayer_condition", "is_retention_agent",
                  "payment_term_days", "price_list", "notes", "active")
        widgets = {
            "taxpayer_status": forms.TextInput(attrs=_text),
            "taxpayer_condition": forms.TextInput(attrs=_text),
            "is_retention_agent": forms.CheckboxInput(attrs=_check),
            "payment_term_days": forms.NumberInput(attrs={**_text, "min": 0}),
            "price_list": forms.Select(attrs=_select),
            "notes": forms.Textarea(attrs=_textarea),
            "active": forms.CheckboxInput(attrs=_check),
        }


class CustomerContactForm(forms.ModelForm):
    class Meta:
        model = SalesCustomerContact
        fields = ("name", "phone", "email", "position")
        widgets = {
            "name": forms.TextInput(attrs=_text),
            "phone": forms.TextInput(attrs=_text),
            "email": forms.EmailInput(attrs=_text),
            "position": forms.TextInput(attrs=_text),
        }


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ("name", "document_number", "address", "phone", "email", "contact_name", "active")
        widgets = {
            "name": forms.TextInput(attrs=_text),
            "document_number": forms.TextInput(attrs=_text),
            "address": forms.TextInput(attrs=_text),
            "phone": forms.TextInput(attrs=_text),
            "email": forms.EmailInput(attrs=_text),
            "contact_name": forms.TextInput(attrs=_text),
            "active": forms.CheckboxInput(attrs=_check),
        }


class CarrierForm(forms.ModelForm):
    class Meta:
        model = Carrier
        fields = ("business_name", "document_number", "license_plate",
                  "driver_name", "driver_license", "phone", "active")
        widgets = {
            "business_name": forms.TextInput(attrs=_text),
            "document_number": forms.TextInput(attrs=_text),
            "license_plate": forms.TextInput(attrs=_text),
            "driver_name": forms.TextInput(attrs=_text),
            "driver_license": forms.TextInput(attrs=_text),
            "phone": forms.TextInput(attrs=_text),
            "active": forms.CheckboxInput(attrs=_check),
        }
