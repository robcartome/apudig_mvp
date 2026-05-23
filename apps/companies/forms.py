"""
companies/forms.py — Formularios de empresa y sucursal.
"""
from django import forms

from .models import Company, CompanyBranding, Store


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ("name", "ruc", "is_active")


class CompanyBrandingForm(forms.ModelForm):
    class Meta:
        model = CompanyBranding
        fields = ("app_logo_url", "pdf_logo_url", "primary_color", "secondary_color")
        widgets = {
            "primary_color": forms.TextInput(attrs={"type": "color"}),
            "secondary_color": forms.TextInput(attrs={"type": "color"}),
        }


class StoreForm(forms.ModelForm):
    class Meta:
        model = Store
        fields = ("company", "name", "address", "active", "lock_movement_edits")
