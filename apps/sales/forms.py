"""
sales/forms.py — Formularios del módulo de ventas.
"""
from django import forms

from .models import BusinessDocumentType, DocumentSeries, SalesQuotation, SalesQuotationLine


class DocumentSeriesForm(forms.ModelForm):
    class Meta:
        model = DocumentSeries
        fields = ("company", "store", "voucher_type", "series", "active")


class QuotationHeaderForm(forms.ModelForm):
    class Meta:
        model = SalesQuotation
        fields = (
            "store",
            "customer",
            "issue_date",
            "valid_until",
            "currency",
            "notes",
        )
        widgets = {
            "issue_date": forms.DateInput(attrs={"type": "date"}),
            "valid_until": forms.DateInput(attrs={"type": "date"}),
        }
