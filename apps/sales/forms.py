"""
sales/forms.py — Formularios del módulo de ventas.
"""
from decimal import Decimal

from django import forms

from apps.core.managers import filter_by_company
from apps.companies.models import Store
from apps.inventory.models import Product
from apps.partners.models import Customer

from .models import (
    BusinessDocumentType,
    DocumentSeries,
    SalesQuotation,
    SalesQuotationLine,
    SaleOrder,
    Voucher,
    TAX_TYPE_CHOICES,
    VOUCHER_TYPE_CHOICES,
    DOC_CATEGORY_CHOICES,
)

# ── Widget constants ──────────────────────────────────────────────────────────

_text = {"class": "form-control"}
_select = {"class": "form-select"}
_check = {"class": "form-check-input"}
_date = {"class": "form-control", "type": "date"}
_textarea = {"class": "form-control", "rows": 3}


class DocumentSeriesForm(forms.ModelForm):
    """Formulario para crear/editar una serie documental."""

    def __init__(self, *args, company_id=None, store_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company_id:
            self.fields["store"].queryset = Store.objects.filter(
                company_id=company_id, active=True
            ).order_by("name")
        self.fields["voucher_type"].widget.attrs.update(_select)
        self.fields["series"].widget.attrs.update(_text)
        self.fields["store"].widget.attrs.update(_select)
        self.fields["active"].widget.attrs.update(_check)

    class Meta:
        model = DocumentSeries
        fields = ("store", "voucher_type", "series", "active")

    def clean_series(self):
        return self.cleaned_data["series"].upper().strip()


class BusinessDocumentTypeForm(forms.ModelForm):
    """Formulario para tipos de documento comercial."""

    class Meta:
        model = BusinessDocumentType
        fields = (
            "code",
            "name",
            "category",
            "is_sunat",
            "sunat_code",
            "affects_stock",
            "affects_accounting",
            "active",
        )
        widgets = {
            "code": forms.TextInput(attrs=_text),
            "name": forms.TextInput(attrs=_text),
            "category": forms.Select(attrs=_select),
            "sunat_code": forms.TextInput(attrs=_text),
            "is_sunat": forms.CheckboxInput(attrs=_check),
            "affects_stock": forms.CheckboxInput(attrs=_check),
            "affects_accounting": forms.CheckboxInput(attrs=_check),
            "active": forms.CheckboxInput(attrs=_check),
        }

    def clean_code(self):
        return self.cleaned_data["code"].upper().strip()


# ── Cotizaciones ──────────────────────────────────────────────────────────────

class QuotationHeaderForm(forms.ModelForm):
    """Cabecera de cotización — campos editables (sin totales ni número de serie)."""

    def __init__(self, *args, company_id=None, store_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = filter_by_company(
            Customer.objects.filter(active=True), company_id
        ).order_by("legal_name")
        self.fields["customer"].widget = forms.HiddenInput()
        self.fields["customer"].required = False
        if company_id and store_id:
            self.fields["series"].queryset = DocumentSeries.objects.filter(
                company_id=company_id,
                store_id=store_id,
                voucher_type="COT",
                active=True,
            )
        self.fields["series"].widget.attrs.update(_select)
        self.fields["store"].widget.attrs.update(_select)
        self.fields["currency"].widget.attrs.update(_select)
        self.fields["notes"].widget.attrs.update(_textarea)
        self.fields["issue_date"].widget.attrs.update({"class": "form-control", "type": "date"})
        self.fields["valid_until"].widget.attrs.update({"class": "form-control", "type": "date"})

    class Meta:
        model = SalesQuotation
        fields = ("store", "customer", "series", "issue_date", "valid_until", "currency", "notes", "internal_reference")
        widgets = {
            "internal_reference": forms.TextInput(attrs=_text),
            "currency": forms.Select(
                choices=[("PEN", "Soles (PEN)"), ("USD", "Dólares (USD)")],
                attrs=_select,
            ),
        }


class QuotationLineForm(forms.Form):
    """Línea individual de cotización (usado en formset)."""

    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(active=True).select_related("unit").order_by("name"),  # noqa: E501
        empty_label=None,
        widget=forms.HiddenInput(),
        required=True,
        error_messages={"required": "Seleccione un producto."},
    )
    description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.HiddenInput(),
    )
    quantity = forms.DecimalField(
        min_value=Decimal("0.0001"),
        max_digits=14,
        decimal_places=4,
        widget=forms.NumberInput(attrs={**_text, "class": "form-control form-control-sm", "step": "0.0001", "min": "0.0001"}),
    )
    unit_price = forms.DecimalField(
        min_value=Decimal("0"),
        max_digits=14,
        decimal_places=6,
        widget=forms.HiddenInput(),
    )
    discount_amount = forms.DecimalField(
        min_value=Decimal("0"),
        max_digits=14,
        decimal_places=2,
        required=False,
        initial=Decimal("0"),
        widget=forms.HiddenInput(),
    )
    tax_type = forms.ChoiceField(
        choices=TAX_TYPE_CHOICES,
        initial="10",
        widget=forms.Select(attrs={**_select, "class": "form-select form-select-sm"}),
    )
    igv_rate = forms.DecimalField(
        min_value=Decimal("0"),
        max_digits=5,
        decimal_places=2,
        initial=Decimal("18"),
        required=False,
        widget=forms.HiddenInput(),
    )
    memo = forms.CharField(
        max_length=1000,
        required=False,
        widget=forms.HiddenInput(),
    )

    def clean_discount_amount(self):
        return self.cleaned_data.get("discount_amount") or Decimal("0")

    def clean_igv_rate(self):
        return self.cleaned_data.get("igv_rate") or Decimal("18")


QuotationLineFormSet = forms.formset_factory(
    QuotationLineForm,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


# ── Órdenes de venta ──────────────────────────────────────────────────────────

class SaleOrderHeaderForm(forms.ModelForm):
    """Cabecera de orden de venta."""

    def __init__(self, *args, company_id=None, store_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = filter_by_company(
            Customer.objects.filter(active=True), company_id
        ).order_by("legal_name")
        self.fields["customer"].widget.attrs.update(_select)
        self.fields["document_type"].queryset = BusinessDocumentType.objects.filter(active=True).order_by("code")
        self.fields["document_type"].widget.attrs.update(_select)
        if company_id and store_id:
            self.fields["series"].queryset = DocumentSeries.objects.filter(
                company_id=company_id,
                store_id=store_id,
                voucher_type="OV",
                active=True,
            )
        self.fields["series"].widget.attrs.update(_select)
        self.fields["store"].widget.attrs.update(_select)
        self.fields["currency"].widget.attrs.update(_select)
        self.fields["notes"].widget.attrs.update(_textarea)
        self.fields["issue_date"].widget.attrs.update({"class": "form-control", "type": "date"})
        self.fields["due_date"].widget.attrs.update({"class": "form-control", "type": "date"})
        self.fields["payment_term_days"].widget.attrs.update(_text)
        self.fields["internal_reference"].widget.attrs.update(_text)

    class Meta:
        model = SaleOrder
        fields = (
            "store",
            "customer",
            "document_type",
            "series",
            "issue_date",
            "due_date",
            "currency",
            "payment_term_days",
            "notes",
            "internal_reference",
        )
        widgets = {
            "currency": forms.Select(
                choices=[("PEN", "Soles (PEN)"), ("USD", "Dólares (USD)")],
                attrs=_select,
            ),
        }


class SaleOrderLineForm(forms.Form):
    """Línea individual de orden de venta (usado en formset)."""

    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(active=True).select_related("unit").order_by("name"),
        empty_label="— Seleccionar producto —",
        widget=forms.Select(attrs=_select),
        error_messages={"required": "Seleccione un producto."},
    )
    description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.TextInput(attrs=_text),
    )
    quantity = forms.DecimalField(
        min_value=Decimal("0.0001"),
        max_digits=14,
        decimal_places=4,
        widget=forms.NumberInput(attrs={**_text, "step": "0.0001", "min": "0.0001"}),
    )
    unit_price = forms.DecimalField(
        min_value=Decimal("0"),
        max_digits=14,
        decimal_places=6,
        widget=forms.NumberInput(attrs={**_text, "step": "0.000001", "min": "0"}),
    )
    discount_amount = forms.DecimalField(
        min_value=Decimal("0"),
        max_digits=14,
        decimal_places=2,
        required=False,
        initial=Decimal("0"),
        widget=forms.NumberInput(attrs={**_text, "step": "0.01", "min": "0"}),
    )
    tax_type = forms.ChoiceField(
        choices=TAX_TYPE_CHOICES,
        initial="10",
        widget=forms.Select(attrs=_select),
    )
    igv_rate = forms.DecimalField(
        min_value=Decimal("0"),
        max_digits=5,
        decimal_places=2,
        initial=Decimal("18"),
        required=False,
        widget=forms.NumberInput(attrs={**_text, "step": "0.01"}),
    )

    def clean_discount_amount(self):
        return self.cleaned_data.get("discount_amount") or Decimal("0")

    def clean_igv_rate(self):
        return self.cleaned_data.get("igv_rate") or Decimal("18")


SaleOrderLineFormSet = forms.formset_factory(
    SaleOrderLineForm,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


# ── Comprobantes ──────────────────────────────────────────────────────────────

# Solo tipos fiscales: Factura (01), Boleta (03), Nota de Crédito (07), Nota de Débito (08)
_VOUCHER_FISCAL_TYPES = [
    ("01", "Factura"),
    ("03", "Boleta de Venta"),
    ("07", "Nota de Crédito"),
    ("08", "Nota de Débito"),
]

_NOTE_REASON_CODES = [
    ("01", "01 - Anulación de la operación"),
    ("02", "02 - Anulación por error en el RUC"),
    ("03", "03 - Corrección por error en la descripción"),
    ("04", "04 - Descuento global"),
    ("05", "05 - Descuento por ítem"),
    ("06", "06 - Devolución total"),
    ("07", "07 - Devolución por ítem"),
    ("08", "08 - Bonificación"),
    ("13", "13 - Ajustes de operaciones de exportación"),
]


class VoucherHeaderForm(forms.ModelForm):
    """Cabecera de comprobante."""

    def __init__(self, *args, company_id=None, store_id=None, voucher_type=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = filter_by_company(
            Customer.objects.filter(active=True), company_id
        ).order_by("legal_name")
        self.fields["customer"].widget.attrs.update(_select)
        self.fields["voucher_type"].widget.attrs.update(_select)
        if company_id and store_id and voucher_type:
            self.fields["series"].queryset = DocumentSeries.objects.filter(
                company_id=company_id,
                store_id=store_id,
                voucher_type=voucher_type,
                active=True,
            )
        self.fields["series"].widget.attrs.update(_select)
        self.fields["store"].widget.attrs.update(_select)
        self.fields["currency"].widget.attrs.update(_select)
        self.fields["notes"].widget.attrs.update(_textarea)
        self.fields["issue_date"].widget.attrs.update({"class": "form-control", "type": "date"})

    class Meta:
        model = Voucher
        fields = (
            "store",
            "customer",
            "voucher_type",
            "series",
            "issue_date",
            "currency",
            "notes",
        )
        widgets = {
            "voucher_type": forms.Select(choices=_VOUCHER_FISCAL_TYPES, attrs=_select),
            "currency": forms.Select(
                choices=[("PEN", "Soles (PEN)"), ("USD", "Dólares (USD)")],
                attrs=_select,
            ),
        }


class VoucherLineForm(forms.Form):
    """Línea individual de comprobante (usado en formset)."""

    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(active=True).select_related("unit").order_by("name"),
        empty_label="— Seleccionar producto —",
        widget=forms.Select(attrs=_select),
        error_messages={"required": "Seleccione un producto."},
    )
    description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.TextInput(attrs=_text),
    )
    quantity = forms.DecimalField(
        min_value=Decimal("0.0001"),
        max_digits=14,
        decimal_places=4,
        widget=forms.NumberInput(attrs={**_text, "step": "0.0001", "min": "0.0001"}),
    )
    unit_price = forms.DecimalField(
        min_value=Decimal("0"),
        max_digits=14,
        decimal_places=6,
        widget=forms.NumberInput(attrs={**_text, "step": "0.000001", "min": "0"}),
    )
    discount_amount = forms.DecimalField(
        min_value=Decimal("0"),
        max_digits=14,
        decimal_places=2,
        required=False,
        initial=Decimal("0"),
        widget=forms.NumberInput(attrs={**_text, "step": "0.01", "min": "0"}),
    )
    tax_type = forms.ChoiceField(
        choices=TAX_TYPE_CHOICES,
        initial="10",
        widget=forms.Select(attrs=_select),
    )
    igv_rate = forms.DecimalField(
        min_value=Decimal("0"),
        max_digits=5,
        decimal_places=2,
        initial=Decimal("18"),
        required=False,
        widget=forms.NumberInput(attrs={**_text, "step": "0.01"}),
    )

    def clean_discount_amount(self):
        return self.cleaned_data.get("discount_amount") or Decimal("0")

    def clean_igv_rate(self):
        return self.cleaned_data.get("igv_rate") or Decimal("18")


VoucherLineFormSet = forms.formset_factory(
    VoucherLineForm,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class CreditNoteReasonForm(forms.Form):
    """Formulario rápido para crear nota de crédito desde un comprobante emitido."""

    reason_code = forms.ChoiceField(
        choices=_NOTE_REASON_CODES,
        label="Motivo",
        widget=forms.Select(attrs=_select),
    )
    reason_description = forms.CharField(
        max_length=200,
        label="Descripción del motivo",
        widget=forms.TextInput(attrs=_text),
    )
    series = forms.ModelChoiceField(
        queryset=DocumentSeries.objects.none(),
        label="Serie nota de crédito",
        widget=forms.Select(attrs=_select),
    )

    def __init__(self, *args, company_id=None, store_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company_id and store_id:
            self.fields["series"].queryset = DocumentSeries.objects.filter(
                company_id=company_id,
                store_id=store_id,
                voucher_type="07",
                active=True,
            )
