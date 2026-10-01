from uuid import UUID

from django import forms

from apps.inventory.models import PriceList, Warehouse
from apps.partners.models import Customer, DocumentType

from .models import PosRegister


class PosRegisterForm(forms.ModelForm):
    class Meta:
        model = PosRegister
        fields = (
            "code", "name", "ticket_series", "default_warehouse",
            "default_price_list", "default_customer", "default_document_type", "active",
        )
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "POS-01"}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Caja principal"}),
            "ticket_series": forms.TextInput(attrs={"class": "form-control", "placeholder": "T01"}),
            "default_warehouse": forms.Select(attrs={"class": "form-select"}),
            "default_price_list": forms.Select(attrs={"class": "form-select"}),
            "default_customer": forms.Select(attrs={"class": "form-select"}),
            "default_document_type": forms.Select(attrs={"class": "form-select"}),
            "active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, company_id, store_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.company_id = UUID(str(company_id))
        self.store_id = UUID(str(store_id))
        self.instance.company_id = self.company_id
        self.instance.store_id = self.store_id
        self.fields["default_warehouse"].queryset = Warehouse.objects.filter(
            store_id=store_id, active=True
        ).order_by("-is_default", "name")
        self.fields["default_price_list"].queryset = PriceList.objects.filter(
            company_id=company_id, active=True
        ).order_by("-is_default", "name")
        self.fields["default_customer"].queryset = Customer.objects.filter(
            company_id=company_id, active=True
        ).order_by("legal_name")
        self.fields["default_document_type"].queryset = DocumentType.objects.filter(
            code__in=("NV", "03", "01"), active=True
        ).order_by("code")
        self.fields["default_warehouse"].required = True
        self.fields["default_customer"].required = True
        self.fields["default_document_type"].required = True

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.company_id = self.company_id
        instance.store_id = self.store_id
        if commit:
            instance.full_clean()
            instance.save()
        return instance
