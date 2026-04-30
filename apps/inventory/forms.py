from decimal import Decimal

from django import forms

from apps.partners.models import Carrier, CoreCustomer, DocumentType, Supplier

from .models import Brand, Category, Movement, MovementDetail, Product, Unit, Warehouse

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

_date = {"class": "form-control", "type": "datetime-local"}
_textarea = {"class": "form-control", "rows": 2}


class MovementHeaderForm(forms.ModelForm):
    """Cabecera común de movimiento. El campo 'type' se fija por la vista."""

    class Meta:
        model = Movement
        fields = ("date", "warehouse", "reason", "reference_doc",
                  "supplier", "customer", "carrier", "document_type")
        widgets = {
            "date": forms.DateTimeInput(attrs=_date),
            "warehouse": forms.Select(attrs=_select),
            "reason": forms.Textarea(attrs=_textarea),
            "reference_doc": forms.TextInput(attrs=_text),
            "supplier": forms.Select(attrs=_select),
            "customer": forms.Select(attrs=_select),
            "carrier": forms.Select(attrs=_select),
            "document_type": forms.Select(attrs=_select),
        }

    def __init__(self, *args, store_id=None, movement_type="ENTRY", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].required = True
        self.fields["reason"].required = False
        self.fields["reference_doc"].required = False
        self.fields["supplier"].required = False
        self.fields["customer"].required = False
        self.fields["carrier"].required = False
        self.fields["document_type"].required = False

        # Scope warehouses to the active store
        if store_id:
            self.fields["warehouse"].queryset = Warehouse.objects.filter(
                store_id=store_id, active=True
            ).order_by("name")
        else:
            self.fields["warehouse"].queryset = Warehouse.objects.none()

        self.fields["supplier"].queryset = Supplier.objects.filter(active=True).order_by("name")
        self.fields["customer"].queryset = CoreCustomer.objects.filter(active=True).order_by("legal_name")
        self.fields["carrier"].queryset = Carrier.objects.filter(active=True).order_by("business_name")
        self.fields["document_type"].queryset = DocumentType.objects.filter(active=True).order_by("code")

        # Show/hide fields by type
        if movement_type == "ENTRY":
            self.fields["customer"].widget = forms.HiddenInput()
        elif movement_type == "EXIT":
            self.fields["supplier"].widget = forms.HiddenInput()
        elif movement_type in ("TRANSFER", "ADJUSTMENT"):
            self.fields["supplier"].widget = forms.HiddenInput()
            self.fields["customer"].widget = forms.HiddenInput()
            self.fields["carrier"].widget = forms.HiddenInput()


class MovementTransferForm(forms.ModelForm):
    """Para transferencias: requiere almacén origen y destino."""

    class Meta:
        model = Movement
        fields = ("date", "warehouse_origin", "warehouse_dest", "reason", "reference_doc")
        widgets = {
            "date": forms.DateTimeInput(attrs=_date),
            "warehouse_origin": forms.Select(attrs=_select),
            "warehouse_dest": forms.Select(attrs=_select),
            "reason": forms.Textarea(attrs=_textarea),
            "reference_doc": forms.TextInput(attrs=_text),
        }

    def __init__(self, *args, store_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reason"].required = False
        self.fields["reference_doc"].required = False
        qs = Warehouse.objects.none()
        if store_id:
            qs = Warehouse.objects.filter(store_id=store_id, active=True).order_by("name")
        self.fields["warehouse_origin"].queryset = qs
        self.fields["warehouse_dest"].queryset = qs

    def clean(self):
        cleaned_data = super().clean()
        origin = cleaned_data.get("warehouse_origin")
        dest = cleaned_data.get("warehouse_dest")
        if origin and dest and origin == dest:
            raise forms.ValidationError("El almacén de origen y destino no pueden ser el mismo.")
        return cleaned_data


class MovementDetailForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(active=True).select_related("unit").order_by("name"),
        widget=forms.Select(attrs=_select),
        label="Producto",
    )
    quantity = forms.DecimalField(
        max_digits=10, decimal_places=3, min_value=Decimal("0.001"),
        widget=forms.NumberInput(attrs={**_text, "step": "0.001", "min": "0.001"}),
        label="Cantidad",
    )
    unit_price = forms.DecimalField(
        max_digits=10, decimal_places=3, min_value=Decimal("0"),
        required=False,
        widget=forms.NumberInput(attrs={**_text, "step": "0.001", "min": "0"}),
        label="P. Unitario",
    )

    def clean_unit_price(self):
        val = self.cleaned_data.get("unit_price")
        return val if val is not None else Decimal("0")


MovementDetailFormSet = forms.formset_factory(
    MovementDetailForm, extra=1, min_num=1, validate_min=True
)

