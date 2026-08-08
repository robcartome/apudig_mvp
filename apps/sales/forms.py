"""
sales/forms.py — Formularios del módulo de ventas.
"""
from decimal import Decimal
from uuid import UUID

from django import forms

from apps.core.managers import filter_by_company
from apps.companies.models import Store
from apps.inventory.models import PriceList, Product, Warehouse
from apps.partners.models import Customer, DocumentType
from apps.users.models import Employee

from .models import (
    DocumentSeries,
    PaymentMethod,
    MeansOfPayment,
    SalesQuotation,
    SalesQuotationLine,
    SaleOrder,
    SalesDocument,
    TAX_TYPE_CHOICES,
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
        self.fields["document_type"].widget.attrs.update(_select)
        self.fields["series"].widget.attrs.update(_text)
        self.fields["store"].widget.attrs.update(_select)
        self.fields["active"].widget.attrs.update(_check)

    class Meta:
        model = DocumentSeries
        fields = ("store", "document_type", "series", "active")

    def clean_series(self):
        return self.cleaned_data["series"].upper().strip()


class DocumentTypeForm(forms.ModelForm):
    """Formulario para tipos de documento comercial."""

    class Meta:
        model = DocumentType
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


class PaymentMethodForm(forms.ModelForm):
    class Meta:
        model = PaymentMethod
        fields = ("name", "is_cash", "active")
        widgets = {
            "name": forms.TextInput(attrs={**_text, "placeholder": "Ej: Contado, Crédito 30 días"}),
            "is_cash": forms.CheckboxInput(attrs=_check),
            "active": forms.CheckboxInput(attrs=_check),
        }


class MeansOfPaymentForm(forms.ModelForm):
    class Meta:
        model = MeansOfPayment
        fields = ("name", "active")
        widgets = {
            "name": forms.TextInput(attrs={**_text, "placeholder": "Ej: Efectivo, Yape, Plin"}),
            "active": forms.CheckboxInput(attrs=_check),
        }


# ── Cotizaciones ──────────────────────────────────────────────────────────────

class QuotationHeaderForm(forms.ModelForm):
    """Cabecera de cotización con serie y correlativo editables."""

    number = forms.CharField(required=False, max_length=8)

    # ── Campos de solo-UI (no se guardan directamente en el modelo) ───────────
    igv_rate_default = forms.ChoiceField(
        label="IGV",
        choices=[("18", "18%"), ("10", "10%"), ("4", "4%"), ("0", "0%")],
        initial="18",
        required=False,
        widget=forms.Select(attrs=_select),
    )
    payment_method = forms.ModelChoiceField(
        queryset=PaymentMethod.objects.none(),
        label="Forma de Pago",
        required=False,
        widget=forms.HiddenInput(),
    )
    means_of_payment = forms.ModelChoiceField(
        queryset=MeansOfPayment.objects.none(),
        label="Medio de Pago",
        required=False,
        widget=forms.HiddenInput(),
    )
    seller_name = forms.CharField(
        label="Vendedor",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={**_text, "placeholder": "—"}),
    )

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
                document_type__code="COT",
                active=True,
            )
        if company_id:
            self.fields["payment_method"].queryset = PaymentMethod.objects.filter(
                company_id=company_id, active=True
            )
            self.fields["means_of_payment"].queryset = MeansOfPayment.objects.filter(
                company_id=company_id, active=True
            )
        self.fields["series"].widget.attrs.update(_select)
        self.fields["store"].widget.attrs.update(_select)
        self.fields["currency"].widget.attrs.update(_select)
        self.fields["notes"].widget.attrs.update(_textarea)
        self.fields["exchange_rate"].widget.attrs.update({**_text, "step": "0.000001", "min": "0"})
        self.fields["exchange_rate"].required = False
        self.fields["number"].widget.attrs.update({
            **_text,
            "readonly": "readonly",
            "inputmode": "numeric",
            "autocomplete": "off",
        })
        if self.instance.pk and self.instance.number and not self.is_bound:
            self.initial["number"] = f"{self.instance.number:08d}"
        # Fechas con datetime-local — se crea un nuevo widget para que input_type se aplique
        # correctamente (DateInput.__init__ hace pop de "type" y lo asigna a input_type)
        for fname in ("issue_date", "valid_until"):
            self.fields[fname].widget = forms.DateInput(
                format='%Y-%m-%dT%H:%M',
                attrs={"class": "form-control", "type": "datetime-local"},
            )
            self.fields[fname].input_formats = [
                '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d',
            ]

    def clean(self):
        cleaned_data = super().clean()
        series = cleaned_data.get("series")
        number = (cleaned_data.get("number") or "").strip()
        if number and (not number.isdigit() or int(number) < 1):
            self.add_error("number", "Ingrese un correlativo numérico mayor que cero.")
        elif series and number:
            numeric_number = int(number)
            cleaned_data["number"] = numeric_number
            duplicate = SalesQuotation.objects.filter(series=series, number=numeric_number)
            if self.instance.pk:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                self.add_error(
                    "number",
                    f"Ya existe la cotización {series.series}-{numeric_number:08d}.",
                )
        return cleaned_data

    class Meta:
        model = SalesQuotation
        fields = (
            "store", "customer", "series", "number", "issue_date", "valid_until",
            "currency", "exchange_rate", "notes", "internal_reference",
            "payment_method", "means_of_payment",
        )
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
        required=False,
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
    extra=0,
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
        self.fields["document_type"].queryset = DocumentType.objects.filter(active=True).order_by("code")
        self.fields["document_type"].widget.attrs.update(_select)
        if company_id and store_id:
            self.fields["series"].queryset = DocumentSeries.objects.filter(
                company_id=company_id,
                store_id=store_id,
                document_type__code="OV",
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


# ── Documentos de venta ──────────────────────────────────────────────────────

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


class SalesDocumentHeaderForm(forms.ModelForm):
    """Cabecera de un documento de venta."""

    number = forms.CharField(required=False, max_length=8)
    manual_number = forms.BooleanField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, company_id=None, store_id=None, document_type=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = filter_by_company(
            Customer.objects.filter(active=True), company_id
        ).order_by("legal_name")
        self.fields["customer"].widget = forms.HiddenInput()
        self.fields["customer"].required = True
        self.fields["store"].queryset = Store.objects.filter(
            company_id=company_id, active=True
        ) if company_id else Store.objects.none()
        if store_id:
            self.fields["store"].queryset = self.fields["store"].queryset.filter(pk=store_id)
        self.fields["document_type"].widget.attrs.update(_select)
        self.fields["document_type"].queryset = DocumentType.objects.filter(
            active=True, category__in=("SALES", "BILLING")
        ).order_by("code")
        selected_document_type = None
        if document_type:
            try:
                selected_document_type = DocumentType.objects.filter(pk=UUID(str(document_type))).first()
            except ValueError:
                selected_document_type = DocumentType.objects.filter(code=document_type).first()
            if selected_document_type and not self.is_bound:
                self.initial["document_type"] = selected_document_type.pk
        if company_id and store_id and document_type:
            self.fields["series"].queryset = DocumentSeries.objects.filter(
                company_id=company_id,
                store_id=store_id,
                document_type=selected_document_type,
                active=True,
            )
        else:
            self.fields["series"].queryset = DocumentSeries.objects.none()
        self.fields["payment_method"].queryset = PaymentMethod.objects.filter(
            company_id=company_id, active=True
        ) if company_id else PaymentMethod.objects.none()
        self.fields["means_of_payment"].queryset = MeansOfPayment.objects.filter(
            company_id=company_id, active=True
        ) if company_id else MeansOfPayment.objects.none()
        self.fields["seller"].queryset = Employee.objects.filter(
            company_id=company_id, is_active=True
        ) if company_id else Employee.objects.none()
        self.fields["price_list"].queryset = PriceList.objects.filter(
            company_id=company_id, active=True
        ) if company_id else PriceList.objects.none()
        self.fields["warehouse"].queryset = Warehouse.objects.filter(
            store_id=store_id, active=True
        ) if store_id else Warehouse.objects.none()
        self.fields["series"].widget.attrs.update(_select)
        self.fields["store"].widget.attrs.update(_select)
        self.fields["currency"].widget.attrs.update(_select)
        for field_name in (
            "payment_method", "means_of_payment", "seller", "price_list", "warehouse"
        ):
            self.fields[field_name].widget.attrs.update(_select)
        self.fields["notes"].widget.attrs.update(_textarea)
        self.fields["issue_date"].widget = forms.DateInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"class": "form-control", "type": "datetime-local"},
        )
        self.fields["issue_date"].input_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
        ]
        self.fields["exchange_rate"].widget.attrs.update({**_text, "step": "0.000001", "min": "0"})
        self.fields["exchange_rate"].required = False
        self.fields["internal_reference"].widget.attrs.update(_text)
        self.fields["register_inventory_movement"].widget.attrs.update(_check)
        self.fields["number"].widget.attrs.update({
            **_text,
            "readonly": "readonly",
            "inputmode": "numeric",
            "autocomplete": "off",
        })
        if self.instance.pk and self.instance.number and not self.is_bound:
            self.initial["manual_number"] = True

    def clean(self):
        cleaned_data = super().clean()
        store = cleaned_data.get("store")
        series = cleaned_data.get("series")
        document_type = cleaned_data.get("document_type")
        warehouse = cleaned_data.get("warehouse")
        number = (cleaned_data.get("number") or "").strip()
        manual_number = cleaned_data.get("manual_number", False)

        if series and store and document_type and (
            series.store_id != store.id or series.document_type_id != document_type.id
        ):
            self.add_error("series", "La serie no corresponde a la sucursal y tipo de documento.")
        if cleaned_data.get("register_inventory_movement") and not warehouse:
            self.add_error("warehouse", "Seleccione un almacén para registrar la salida.")
        if warehouse and store and warehouse.store_id != store.id:
            self.add_error("warehouse", "El almacén no pertenece a la sucursal seleccionada.")
        if manual_number:
            if not number.isdigit() or int(number) < 1:
                self.add_error("number", "Ingrese un correlativo numérico mayor que cero.")
            elif len(number) > 8:
                self.add_error("number", "El correlativo admite como máximo 8 dígitos.")
            else:
                cleaned_data["number"] = number.zfill(8)
        else:
            cleaned_data["number"] = ""
        return cleaned_data

    class Meta:
        model = SalesDocument
        fields = (
            "store",
            "customer",
            "document_type",
            "series",
            "number",
            "manual_number",
            "issue_date",
            "currency",
            "exchange_rate",
            "payment_method",
            "means_of_payment",
            "seller",
            "price_list",
            "register_inventory_movement",
            "warehouse",
            "notes",
            "internal_reference",
        )
        widgets = {
            "currency": forms.Select(
                choices=[("PEN", "Soles (PEN)"), ("USD", "Dólares (USD)")],
                attrs=_select,
            ),
            "register_inventory_movement": forms.CheckboxInput(attrs=_check),
        }


class SalesDocumentLineForm(forms.Form):
    """Línea individual de documento de venta (usada en formset).

    Usa HiddenInput para campos que maneja el ProductPicker JS,
    igual que QuotationLineForm.
    """

    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(active=True).select_related("unit").order_by("name"),
        empty_label=None,
        widget=forms.HiddenInput(),
        required=False,
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


SalesDocumentLineFormSet = forms.formset_factory(
    SalesDocumentLineForm,
    extra=0,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class CreditNoteReasonForm(forms.Form):
    """Formulario para crear una nota de crédito desde un documento emitido."""

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
                document_type__code="07",
                active=True,
            )
