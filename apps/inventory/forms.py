from django import forms

from .models import Brand, Category, Product, Unit, Warehouse

_text = {"class": "form-control"}
_select = {"class": "form-select"}
_check = {"class": "form-check-input"}


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ("code", "name", "active")
        widgets = {
            "code": forms.TextInput(attrs={**_text, "placeholder": "Ej: ELEC"}),
            "name": forms.TextInput(attrs={**_text, "placeholder": "Electrónica"}),
            "active": forms.CheckboxInput(attrs=_check),
        }


class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = ("name", "active")
        widgets = {
            "name": forms.TextInput(attrs={**_text, "placeholder": "Nombre de marca"}),
            "active": forms.CheckboxInput(attrs=_check),
        }


class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ("code", "name")
        widgets = {
            "code": forms.TextInput(attrs={**_text, "placeholder": "Ej: UND"}),
            "name": forms.TextInput(attrs={**_text, "placeholder": "Unidad"}),
        }


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ("name", "description", "active", "is_default")
        widgets = {
            "name": forms.TextInput(attrs={**_text, "placeholder": "Almacén principal"}),
            "description": forms.TextInput(attrs={**_text, "placeholder": "Descripción (opcional)"}),
            "active": forms.CheckboxInput(attrs=_check),
            "is_default": forms.CheckboxInput(attrs=_check),
        }

    def __init__(self, *args, store=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._store = store

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self._store is not None:
            instance.store_id = self._store
        if commit:
            instance.save()
        return instance


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = (
            "name", "sku", "barcode", "description", "model",
            "price_purchase", "price_sale",
            "category", "brand", "unit", "active",
        )
        widgets = {
            "name": forms.TextInput(attrs={**_text, "placeholder": "Nombre del producto"}),
            "sku": forms.TextInput(attrs={**_text, "placeholder": "SKU único"}),
            "barcode": forms.TextInput(attrs={**_text, "placeholder": "Código de barras"}),
            "description": forms.Textarea(attrs={**_text, "rows": 3}),
            "model": forms.TextInput(attrs=_text),
            "price_purchase": forms.NumberInput(attrs={**_text, "step": "0.01"}),
            "price_sale": forms.NumberInput(attrs={**_text, "step": "0.01"}),
            "category": forms.Select(attrs=_select),
            "brand": forms.Select(attrs=_select),
            "unit": forms.Select(attrs=_select),
            "active": forms.CheckboxInput(attrs=_check),
        }

