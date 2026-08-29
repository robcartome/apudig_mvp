from decimal import Decimal

from django import forms
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.partners.models import Carrier, Customer, DocumentType, Supplier

from .models import Brand, Category, Movement, MovementDetail, MovementType, PriceList, Product, ProductPrice, ProductSupplier, ProductUnit, Unit, Warehouse, WarehouseLocation

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

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._company = company

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self._company is not None:
            instance.company = self._company
        if commit:
            instance.save()
        return instance


class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = ("name", "active")
        widgets = {
            "name": forms.TextInput(attrs={**_text, "placeholder": "Nombre de marca"}),
            "active": forms.CheckboxInput(attrs=_check),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._company = company

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self._company is not None:
            instance.company = self._company
        if commit:
            instance.save()
        return instance


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


class WarehouseLocationForm(forms.ModelForm):
    class Meta:
        model = WarehouseLocation
        fields = ("warehouse", "code", "name", "description", "active")
        widgets = {
            "warehouse": forms.Select(attrs=_select),
            "code": forms.TextInput(attrs={**_text, "placeholder": "Ej: A-01, PASILLO-B"}),
            "name": forms.TextInput(attrs={**_text, "placeholder": "Pasillo A estante 1"}),
            "description": forms.TextInput(attrs={**_text, "placeholder": "Descripción (opcional)"}),
            "active": forms.CheckboxInput(attrs=_check),
        }

    def __init__(self, *args, store_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        if store_id:
            self.fields["warehouse"].queryset = Warehouse.objects.filter(
                store_id=store_id, active=True
            ).order_by("name")
        else:
            self.fields["warehouse"].queryset = Warehouse.objects.filter(active=True).order_by("name")


class ProductForm(forms.ModelForm):
    image_file = forms.ImageField(
        required=False,
        label="Imagen del producto",
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control product-image-input", "accept": "image/jpeg,image/png,image/webp"}
        ),
    )
    remove_image = forms.BooleanField(required=False, label="Quitar imagen")
    secondary_image_file = forms.ImageField(
        required=False,
        label="Imagen secundaria",
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control product-image-input", "accept": "image/jpeg,image/png,image/webp"}
        ),
    )
    remove_secondary_image = forms.BooleanField(required=False, label="Quitar imagen secundaria")
    tertiary_image_file = forms.ImageField(
        required=False,
        label="Imagen adicional",
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control product-image-input", "accept": "image/jpeg,image/png,image/webp"}
        ),
    )
    remove_tertiary_image = forms.BooleanField(required=False, label="Quitar imagen adicional")

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
            "price_purchase": forms.NumberInput(attrs={**_text, "step": "0.01", "placeholder": "0"}),
            "price_sale": forms.NumberInput(attrs={**_text, "step": "0.01"}),
            "category": forms.HiddenInput(),
            "brand": forms.HiddenInput(),
            "unit": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "active": forms.CheckboxInput(attrs=_check),
        }

    def _clean_product_image(self, field_name):
        image = self.cleaned_data.get(field_name)
        if not image:
            return image
        allowed_types = {"image/jpeg", "image/png", "image/webp"}
        if getattr(image, "content_type", "") not in allowed_types:
            raise forms.ValidationError("Formato no permitido. Usa JPEG, PNG o WebP.")
        if image.size > settings.PRODUCT_IMAGE_MAX_SIZE:
            max_mb = settings.PRODUCT_IMAGE_MAX_SIZE // (1024 * 1024)
            raise forms.ValidationError(f"La imagen no debe superar {max_mb} MB.")
        return image

    def clean_image_file(self):
        return self._clean_product_image("image_file")

    def clean_secondary_image_file(self):
        return self._clean_product_image("secondary_image_file")

    def clean_tertiary_image_file(self):
        return self._clean_product_image("tertiary_image_file")

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._company = company
        if not self.is_bound and not self.instance.pk:
            self.fields["unit"].initial = Unit.objects.filter(code="NIU").first()
        max_mb = settings.PRODUCT_IMAGE_MAX_SIZE / (1024 * 1024)
        help_text = f"JPEG, PNG o WebP. Máximo {max_mb:g} MB."
        for field_name in ("image_file", "secondary_image_file", "tertiary_image_file"):
            self.fields[field_name].help_text = help_text
        if company is not None:
            self.fields["category"].queryset = Category.objects.filter(
                company=company, active=True
            ).order_by("name")
            self.fields["brand"].queryset = Brand.objects.filter(
                company=company, active=True
            ).order_by("name")

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self._company is not None:
            instance.company = self._company
        if commit:
            instance.save()
        return instance


class ProductUnitForm(forms.ModelForm):
    class Meta:
        model = ProductUnit
        fields = (
            "unit", "conversion_factor", "sale_price", "purchase_price", "active",
        )
        widgets = {
            "unit": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "conversion_factor": forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.000001", "min": "0.000001"}),
            "sale_price": forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.000001", "min": "0"}),
            "purchase_price": forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.000001", "min": "0"}),
            "active": forms.CheckboxInput(attrs=_check),
        }


class BaseProductUnitFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        for form in self.forms:
            data = getattr(form, "cleaned_data", None) or {}
            if not data or data.get("DELETE"):
                continue
            if self.instance.unit_id and data.get("unit") == self.instance.unit:
                raise forms.ValidationError(
                    "La unidad principal no debe repetirse como presentación adicional."
                )


ProductUnitFormSet = forms.inlineformset_factory(
    Product, ProductUnit, form=ProductUnitForm, formset=BaseProductUnitFormSet,
    extra=2, can_delete=True,
)


class ProductSupplierForm(forms.ModelForm):
    class Meta:
        model = ProductSupplier
        fields = (
            "supplier", "supplier_code", "supplier_product_name",
            "supplier_description", "purchase_price", "is_preferred", "active",
        )
        widgets = {
            "supplier": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "supplier_code": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "supplier_product_name": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "supplier_description": forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
            "purchase_price": forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.000001", "min": "0"}),
            "is_preferred": forms.CheckboxInput(attrs=_check),
            "active": forms.CheckboxInput(attrs=_check),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._company = company
        if company is None:
            self.fields["supplier"].queryset = Supplier.objects.none()
        else:
            self.fields["supplier"].queryset = Supplier.objects.filter(
                Q(active=True) | Q(pk=self.instance.supplier_id), company=company
            ).order_by("name")

    def _post_clean(self):
        if self._company is not None:
            self.instance.company = self._company
        super()._post_clean()

    def clean_supplier_code(self):
        supplier_code = (self.cleaned_data.get("supplier_code") or "").strip()
        supplier = self.cleaned_data.get("supplier")
        if self._company and supplier and supplier_code:
            duplicates = ProductSupplier.objects.filter(
                company=self._company,
                supplier=supplier,
                supplier_code=supplier_code,
            )
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise forms.ValidationError(
                    "Este proveedor ya utiliza este código en otro producto."
                )
        return supplier_code

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self._company is not None:
            instance.company = self._company
        if commit:
            instance.save()
        return instance


class BaseProductSupplierFormSet(forms.BaseInlineFormSet):
    def __init__(self, *args, company=None, **kwargs):
        self.company = company
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["company"] = self.company
        return kwargs

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        suppliers = set()
        codes = set()
        preferred = 0
        for form in self.forms:
            data = getattr(form, "cleaned_data", None) or {}
            if not data or data.get("DELETE"):
                continue
            supplier = data.get("supplier")
            code = (data.get("supplier_code") or "").strip()
            if supplier and supplier.pk in suppliers:
                raise forms.ValidationError("No se puede repetir un proveedor para el mismo producto.")
            if supplier:
                suppliers.add(supplier.pk)
            if supplier and code:
                key = (supplier.pk, code)
                if key in codes:
                    raise forms.ValidationError("El código de proveedor no puede repetirse.")
                codes.add(key)
            if data.get("is_preferred"):
                preferred += 1
        if preferred > 1:
            raise forms.ValidationError("Solo un proveedor puede marcarse como preferido.")


ProductSupplierFormSet = forms.inlineformset_factory(
    Product, ProductSupplier, form=ProductSupplierForm,
    formset=BaseProductSupplierFormSet, extra=2, can_delete=True,
)

_date = {"class": "form-control", "type": "datetime-local"}
_date_format = "%Y-%m-%dT%H:%M"
_date_input_formats = (
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)
_textarea = {"class": "form-control", "rows": 2}


def _set_default_movement_date(form):
    """Set the current local datetime only for new, unbound movements."""
    if form.is_bound or form.instance.pk or form.initial.get("date"):
        return
    form.initial["date"] = timezone.localtime().strftime(_date_format)


class MovementHeaderForm(forms.ModelForm):
    """Cabecera común de movimiento. El campo 'type' se fija por la vista."""

    class Meta:
        model = Movement
        fields = ("date", "warehouse", "series", "number",
                  "reason", "reference_doc", "description",
                  "supplier", "customer", "carrier", "document_type")
        widgets = {
            "date": forms.DateTimeInput(format=_date_format, attrs=_date),
            "warehouse": forms.Select(attrs=_select),
            "series": forms.TextInput(attrs={**_text, "placeholder": "0000"}),
            "number": forms.TextInput(attrs={**_text, "placeholder": "0"}),
            "reason": forms.HiddenInput(),
            "reference_doc": forms.TextInput(attrs=_text),
            "description": forms.Textarea(attrs={**_text, "rows": 2, "placeholder": "Información adicional (opcional)"}),
            "supplier": forms.HiddenInput(),
            "customer": forms.HiddenInput(),
            "carrier": forms.Select(attrs=_select),
            "document_type": forms.Select(attrs=_select),
        }

    def __init__(self, *args, store_id=None, company_id=None, movement_type="ENTRY", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].input_formats = _date_input_formats
        _set_default_movement_date(self)
        self.fields["date"].required = True
        self.fields["warehouse"].required = movement_type in (
            MovementType.ENTRY,
            MovementType.EXIT,
            MovementType.ADJUSTMENT,
        )
        self.fields["reason"].required = False
        self.fields["series"].required = False
        self.fields["number"].required = False
        self.fields["reference_doc"].required = False
        self.fields["description"].required = False
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
        self.fields["customer"].queryset = Customer.objects.filter(active=True).order_by("legal_name")
        self.fields["carrier"].queryset = Carrier.objects.filter(active=True).order_by("business_name")
        if company_id:
            self.fields["supplier"].queryset = self.fields["supplier"].queryset.filter(company_id=company_id)
            self.fields["customer"].queryset = self.fields["customer"].queryset.filter(company_id=company_id)
            self.fields["carrier"].queryset = self.fields["carrier"].queryset.filter(company_id=company_id)
        else:
            self.fields["supplier"].queryset = Supplier.objects.none()
            self.fields["customer"].queryset = Customer.objects.none()
            self.fields["carrier"].queryset = Carrier.objects.none()
        self.fields["document_type"].queryset = DocumentType.objects.filter(active=True).order_by("code")

        # Show/hide fields by type
        if movement_type in (MovementType.TRANSFER, MovementType.ADJUSTMENT):
            self.fields["carrier"].widget = forms.HiddenInput()


class MovementTransferForm(forms.ModelForm):
    """Para transferencias: requiere almacén origen y destino."""

    class Meta:
        model = Movement
        fields = ("date", "warehouse_origin", "warehouse_dest",
                  "reason", "reference_doc", "description")
        widgets = {
            "date": forms.DateTimeInput(format=_date_format, attrs=_date),
            "warehouse_origin": forms.Select(attrs=_select),
            "warehouse_dest": forms.Select(attrs=_select),
            "reason": forms.HiddenInput(),
            "reference_doc": forms.TextInput(attrs=_text),
            "description": forms.Textarea(attrs={**_text, "rows": 2, "placeholder": "Información adicional (opcional)"}),
        }

    def __init__(self, *args, store_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].input_formats = _date_input_formats
        _set_default_movement_date(self)
        self.fields["warehouse_origin"].required = True
        self.fields["warehouse_dest"].required = True
        self.fields["reason"].required = False
        self.fields["reference_doc"].required = False
        self.fields["description"].required = False
        qs = Warehouse.objects.none()
        if store_id:
            qs = Warehouse.objects.for_store(store_id).filter(active=True).order_by("name")
        self.fields["warehouse_origin"].queryset = qs
        self.fields["warehouse_dest"].queryset = qs

    def clean(self):
        cleaned_data = super().clean()
        origin = cleaned_data.get("warehouse_origin")
        dest = cleaned_data.get("warehouse_dest")
        if origin and dest and origin == dest:
            raise forms.ValidationError("El almacén de origen y destino no pueden ser el mismo.")
        return cleaned_data


_sm = "form-control form-control-sm"


class MovementDetailForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(active=True).select_related("unit").order_by("name"),
        widget=forms.HiddenInput(),  # UI managed by JS product-picker
        label="Producto",
    )
    unit = forms.UUIDField(required=False, widget=forms.HiddenInput())
    quantity = forms.DecimalField(
        max_digits=10, decimal_places=3, min_value=Decimal("0.001"),
        widget=forms.NumberInput(attrs={"class": _sm, "step": "0.001", "min": "0.001"}),
        label="Cantidad",
    )
    unit_price = forms.DecimalField(
        max_digits=10, decimal_places=3, min_value=Decimal("0"),
        required=False,
        widget=forms.NumberInput(attrs={"class": _sm, "step": "0.001", "min": "0"}),
        label="P. Unitario",
    )
    location = forms.UUIDField(
        required=False,
        widget=forms.HiddenInput(),
        label="Ubicación",
    )

    def __init__(self, *args, company_id=None, allow_zero=False, **kwargs):
        super().__init__(*args, **kwargs)
        if allow_zero:
            self.fields["quantity"] = forms.DecimalField(
                max_digits=10,
                decimal_places=3,
                min_value=Decimal("0"),
                widget=forms.NumberInput(
                    attrs={"class": _sm, "step": "0.001", "min": "0"}
                ),
                label="Cantidad",
            )
        if company_id:
            self.fields["product"].queryset = (
                Product.objects
                .filter(active=True, company_id=company_id)
                .select_related("unit")
                .order_by("name")
            )

    def clean_unit_price(self):
        val = self.cleaned_data.get("unit_price")
        return val if val is not None else Decimal("0")


MovementDetailFormSet = forms.formset_factory(
    MovementDetailForm, extra=1, min_num=1, validate_min=True
)

MovementDetailEditFormSet = forms.formset_factory(
    MovementDetailForm, extra=0, min_num=1, validate_min=True
)


# ── Listas de precio ──────────────────────────────────────────────────────────────────

class PriceListForm(forms.ModelForm):
    class Meta:
        model = PriceList
        fields = ("name", "description", "active")
        widgets = {
            "name": forms.TextInput(attrs={**_text, "placeholder": "Ej: Lista minorista"}),
            "description": forms.TextInput(attrs={**_text, "placeholder": "Descripción (opcional)"}),
            "active": forms.CheckboxInput(attrs=_check),
        }


class ProductPriceForm(forms.Form):
    """Usado en el formset de precios dentro del detalle de lista."""
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(active=True).select_related("unit").order_by("name"),
        empty_label="— Seleccionar producto —",
        widget=forms.Select(attrs=_select),
    )
    amount = forms.DecimalField(
        min_value=Decimal("0"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={**_text, "step": "0.01", "min": "0"}),
    )
    currency = forms.ChoiceField(
        choices=[("PEN", "Soles (PEN)"), ("USD", "Dólares (USD)")],
        initial="PEN",
        widget=forms.Select(attrs=_select),
    )

    def __init__(self, *args, company_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company_id:
            self.fields["product"].queryset = (
                Product.objects
                .filter(active=True, company_id=company_id)
                .select_related("unit")
                .order_by("name")
            )


ProductPriceFormSet = forms.formset_factory(
    ProductPriceForm, extra=1, min_num=0, validate_min=False, can_delete=True
)


class BulkImportForm(forms.Form):
    file = forms.FileField(
        label="Archivo",
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".xlsx,.csv"}),
        help_text="Formatos permitidos: .xlsx, .csv",
    )
    dry_run = forms.BooleanField(
        required=False,
        initial=True,
        label="Solo validar (no guardar)",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
