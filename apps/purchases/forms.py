from decimal import Decimal

from django import forms

from apps.inventory.models import Product, Unit, Warehouse
from apps.partners.models import DocumentType, Supplier
from apps.sales.models import MeansOfPayment, PaymentMethod

from .models import (
    LandedCostAllocationMethod, PurchaseCategory, PurchaseDocument,
    PurchaseDocumentLine, PurchaseOrder, PurchaseOrderLine, PurchaseTaxType,
)


_text = {"class": "form-control"}
_select = {"class": "form-select"}
_quantity = {
    "class": "form-control form-control-sm text-end quantity-input",
    "inputmode": "decimal", "autocomplete": "off", "maxlength": "15",
}


class PurchaseDocumentForm(forms.ModelForm):
    class Meta:
        model = PurchaseDocument
        fields = (
            "supplier", "purchase_order", "document_type", "series", "number", "payment_method", "issue_date", "due_date",
            "currency", "exchange_rate", "register_inventory_movement", "warehouse",
            "notes", "internal_reference",
        )
        widgets = {
            "supplier": forms.HiddenInput(),
            "purchase_order": forms.Select(attrs=_select),
            "document_type": forms.Select(attrs=_select),
            "series": forms.TextInput(attrs=_text),
            "number": forms.TextInput(attrs=_text),
            "payment_method": forms.Select(attrs=_select),
            # HTML date inputs only display ISO values (YYYY-MM-DD).  An
            # explicit format also keeps existing dates visible when editing.
            "issue_date": forms.DateInput(format="%Y-%m-%d", attrs={**_text, "type": "date"}),
            "due_date": forms.DateInput(format="%Y-%m-%d", attrs={**_text, "type": "date"}),
            "currency": forms.Select(choices=(("PEN", "Soles (PEN)"), ("USD", "Dolares (USD)")), attrs=_select),
            "exchange_rate": forms.NumberInput(attrs={**_text, "step": "0.000001", "min": "0.000001"}),
            "register_inventory_movement": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "warehouse": forms.Select(attrs=_select),
            "notes": forms.Textarea(attrs={**_text, "rows": 3}),
            "internal_reference": forms.TextInput(attrs=_text),
        }

    def __init__(self, *args, company_id=None, store_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["issue_date"].input_formats = ["%Y-%m-%d"]
        self.fields["due_date"].input_formats = ["%Y-%m-%d"]
        if company_id and not self.instance.company_id:
            self.instance.company_id = company_id
        # ModelForm ejecuta PurchaseDocument.clean() durante is_valid(). La
        # sucursal no es un campo editable del formulario, por lo que debe
        # mantenerse sincronizada con el alcance activo antes de esa validación.
        if store_id:
            self.instance.store_id = store_id
        self.fields["supplier"].queryset = Supplier.objects.filter(
            company_id=company_id, active=True
        ).order_by("name") if company_id else Supplier.objects.none()
        self.fields["payment_method"].queryset = PaymentMethod.objects.filter(
            company_id=company_id, active=True
        ).order_by("name") if company_id else PaymentMethod.objects.none()
        self.fields["purchase_order"].queryset = PurchaseOrder.objects.filter(
            company_id=company_id, store_id=store_id,
            status__in=("APPROVED", "CLOSED"),
        ).select_related("supplier").order_by("-order_date") if company_id and store_id else PurchaseOrder.objects.none()
        self.fields["document_type"].queryset = DocumentType.objects.filter(
            active=True, category__in=("SALES", "BILLING")
        ).order_by("code")
        self.fields["warehouse"].queryset = Warehouse.objects.filter(
            store_id=store_id, active=True
        ).order_by("name") if store_id else Warehouse.objects.none()

    def clean_series(self):
        return (self.cleaned_data.get("series") or "").strip().upper()

    def clean_number(self):
        return (self.cleaned_data.get("number") or "").strip()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("currency") == "PEN":
            cleaned["exchange_rate"] = Decimal("1")
            self.instance.exchange_rate = Decimal("1")
        payment_method = cleaned.get("payment_method")
        issue_date = cleaned.get("issue_date")
        if payment_method and payment_method.is_cash and issue_date:
            cleaned["due_date"] = issue_date
            self.instance.due_date = issue_date
        elif payment_method and not payment_method.is_cash and not cleaned.get("due_date"):
            self.add_error("due_date", "Indica la fecha de vencimiento para una compra a credito.")
        return cleaned


class PurchaseDocumentLineForm(forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.none(), widget=forms.HiddenInput())
    description = forms.CharField(max_length=500, required=False, widget=forms.HiddenInput())
    unit = forms.ModelChoiceField(queryset=Unit.objects.all().order_by("code"), required=False, widget=forms.HiddenInput())
    quantity = forms.DecimalField(min_value=Decimal("0.0001"), max_digits=14, decimal_places=4, widget=forms.TextInput(attrs=_quantity))
    unit_price = forms.DecimalField(min_value=0, max_digits=14, decimal_places=6, widget=forms.NumberInput(attrs={"class": "form-control form-control-sm text-end value-unit-input", "step": "0.000001", "inputmode": "decimal", "placeholder": "0.00"}))
    discount_amount = forms.DecimalField(min_value=0, max_digits=14, decimal_places=2, required=False, initial=0, widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01"}))
    tax_type = forms.ChoiceField(choices=PurchaseTaxType.choices, initial=PurchaseTaxType.TAXED, widget=forms.Select(attrs={"class": "form-select form-select-sm"}))
    igv_rate = forms.DecimalField(min_value=0, max_digits=5, decimal_places=2, required=False, initial=18, widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01"}))
    update_purchase_price = forms.BooleanField(required=False, initial=True, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    memo = forms.CharField(max_length=1000, required=False, widget=forms.HiddenInput())

    def __init__(self, *args, company_id=None, default_igv_rate=18, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["igv_rate"].initial = default_igv_rate
        self.fields["product"].queryset = Product.objects.filter(
            company_id=company_id, active=True
        ).select_related("unit").order_by("name") if company_id else Product.objects.none()

    def clean_discount_amount(self):
        return self.cleaned_data.get("discount_amount") or Decimal("0")

    def clean_igv_rate(self):
        return self.cleaned_data.get("igv_rate") or Decimal("0")


PurchaseDocumentLineFormSet = forms.formset_factory(
    PurchaseDocumentLineForm, extra=1, min_num=1, validate_min=True, can_delete=True
)


class PurchaseExpenseLineForm(forms.Form):
    purchase_category = forms.ModelChoiceField(
        queryset=PurchaseCategory.objects.none(),
        widget=forms.Select(attrs=_select),
        label="Categoría del gasto",
    )
    description = forms.CharField(max_length=500, widget=forms.TextInput(attrs=_text))
    quantity = forms.DecimalField(
        min_value=Decimal("0.0001"), max_digits=14, decimal_places=4, initial=1,
        widget=forms.TextInput(attrs=_quantity),
    )
    unit_price = forms.DecimalField(
        min_value=0, max_digits=14, decimal_places=6,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm text-end price-unit-input", "step": "0.000001", "inputmode": "decimal", "placeholder": "0.00"}),
        label="Valor unitario",
    )
    discount_amount = forms.DecimalField(required=False, initial=0, min_value=0, max_digits=14, decimal_places=2, widget=forms.HiddenInput())
    tax_type = forms.ChoiceField(choices=PurchaseTaxType.choices, initial=PurchaseTaxType.TAXED, widget=forms.Select(attrs=_select))
    igv_rate = forms.DecimalField(required=False, initial=18, min_value=0, max_digits=5, decimal_places=2, widget=forms.HiddenInput())
    memo = forms.CharField(required=False, max_length=1000, widget=forms.Textarea(attrs={**_text, "rows": 2}))

    def __init__(self, *args, company_id=None, default_igv_rate=18, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["igv_rate"].initial = default_igv_rate
        self.fields["purchase_category"].queryset = PurchaseCategory.objects.filter(
            company_id=company_id, active=True
        ).order_by("name") if company_id else PurchaseCategory.objects.none()

    def clean(self):
        cleaned = super().clean()
        cleaned.update(product=None, unit=None, update_purchase_price=False)
        return cleaned


PurchaseExpenseLineFormSet = forms.formset_factory(
    PurchaseExpenseLineForm, extra=1, min_num=1, validate_min=True, can_delete=True
)


class PurchaseCategoryForm(forms.ModelForm):
    class Meta:
        model = PurchaseCategory
        fields = ("code", "name", "active")
        widgets = {
            "code": forms.TextInput(attrs={**_text, "maxlength": 50}),
            "name": forms.TextInput(attrs={**_text, "maxlength": 200}),
            "active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, company_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company_id = company_id

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        qs = PurchaseCategory.objects.filter(company_id=self.company_id, code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe una categoria de gasto con este codigo.")
        return code


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = (
            "supplier", "order_number", "order_date", "expected_date",
            "currency", "exchange_rate", "notes",
        )
        widgets = {
            "supplier": forms.HiddenInput(),
            "order_number": forms.TextInput(attrs=_text),
            "order_date": forms.DateInput(attrs={**_text, "type": "date"}),
            "expected_date": forms.DateInput(attrs={**_text, "type": "date"}),
            "currency": forms.Select(choices=(("PEN", "Soles (PEN)"), ("USD", "Dolares (USD)")), attrs=_select),
            "exchange_rate": forms.NumberInput(attrs={**_text, "step": "0.000001", "min": "0.000001"}),
            "notes": forms.Textarea(attrs={**_text, "rows": 3}),
        }

    def __init__(self, *args, company_id=None, store_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company_id and not self.instance.company_id:
            self.instance.company_id = company_id
        if store_id and not self.instance.store_id:
            self.instance.store_id = store_id
        self.fields["supplier"].queryset = Supplier.objects.filter(
            company_id=company_id, active=True
        ).order_by("name") if company_id else Supplier.objects.none()

    def clean_order_number(self):
        return (self.cleaned_data.get("order_number") or "").strip().upper()


PurchaseOrderLineFormSet = forms.formset_factory(
    PurchaseDocumentLineForm, extra=1, min_num=1, validate_min=True, can_delete=True
)


class PurchaseReceiptForm(forms.Form):
    warehouse = forms.ModelChoiceField(queryset=Warehouse.objects.none(), widget=forms.Select(attrs=_select))
    receipt_number = forms.CharField(max_length=30, widget=forms.TextInput(attrs=_text))
    receipt_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={**_text, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M")
    )
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={**_text, "rows": 2}))

    def __init__(self, *args, store_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["warehouse"].queryset = Warehouse.objects.filter(store_id=store_id, active=True).order_by("name")


class PurchaseReceiptLineForm(forms.Form):
    purchase_order_line = forms.ModelChoiceField(
        queryset=PurchaseOrderLine.objects.none(), widget=forms.HiddenInput()
    )
    quantity = forms.DecimalField(
        required=False, min_value=0, max_digits=14, decimal_places=4,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.0001", "min": "0"}),
    )

    def __init__(self, *args, order=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["purchase_order_line"].queryset = order.lines.all() if order else PurchaseOrderLine.objects.none()


PurchaseReceiptLineFormSet = forms.formset_factory(PurchaseReceiptLineForm, extra=0)


class SupplierPaymentForm(forms.Form):
    payment_number = forms.CharField(max_length=30, widget=forms.TextInput(attrs=_text))
    payment_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={**_text, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M")
    )
    amount = forms.DecimalField(
        min_value=Decimal("0.01"), max_digits=14, decimal_places=2,
        widget=forms.NumberInput(attrs={**_text, "step": "0.01", "min": "0.01"}),
    )
    means_of_payment = forms.ModelChoiceField(
        queryset=MeansOfPayment.objects.none(), widget=forms.Select(attrs=_select)
    )
    reference = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs=_text))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={**_text, "rows": 2}))

    def __init__(self, *args, company_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["means_of_payment"].queryset = MeansOfPayment.objects.filter(
            company_id=company_id, active=True
        ).order_by("name") if company_id else MeansOfPayment.objects.none()

    def clean_payment_number(self):
        return (self.cleaned_data.get("payment_number") or "").strip().upper()


class PurchaseInstallmentForm(forms.Form):
    due_date = forms.DateField(widget=forms.DateInput(attrs={**_text, "type": "date"}))
    amount = forms.DecimalField(
        min_value=Decimal("0.01"), max_digits=14, decimal_places=2,
        widget=forms.NumberInput(attrs={**_text, "step": "0.01", "min": "0.01"}),
    )


PurchaseInstallmentFormSet = forms.formset_factory(
    PurchaseInstallmentForm, extra=0, min_num=1, validate_min=True
)


class PurchaseLandedCostForm(forms.Form):
    description = forms.CharField(max_length=200, widget=forms.TextInput(attrs=_text))
    reference = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs=_text))
    amount = forms.DecimalField(
        min_value=Decimal("0.01"), max_digits=14, decimal_places=2,
        widget=forms.NumberInput(attrs={**_text, "step": "0.01", "min": "0.01"}),
    )
    allocation_method = forms.ChoiceField(
        choices=LandedCostAllocationMethod.choices, widget=forms.Select(attrs=_select)
    )
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={**_text, "rows": 2}))


class PurchaseLandedCostAllocationForm(forms.Form):
    line = forms.ModelChoiceField(queryset=PurchaseDocumentLine.objects.none(), widget=forms.HiddenInput())
    amount = forms.DecimalField(
        required=False, min_value=0, max_digits=14, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm manual-allocation", "step": "0.01", "min": "0"}),
    )

    def __init__(self, *args, document=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["line"].queryset = document.lines.all() if document else PurchaseDocumentLine.objects.none()


PurchaseLandedCostAllocationFormSet = forms.formset_factory(
    PurchaseLandedCostAllocationForm, extra=0
)
