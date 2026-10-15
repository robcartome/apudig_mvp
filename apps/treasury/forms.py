from decimal import Decimal
from pathlib import Path

from django import forms
from django.conf import settings
from django.utils import timezone

from apps.partners.models import Supplier
from apps.pos.models import PosRegister
from apps.purchases.models import PurchaseCategory, PurchaseDocument

from .models import (
    Bank, BankAccount, BankMovement, BankStatement, CashSafeCount, CashSafeMovement,
    TreasuryFund,
)


class CashSafeCountForm(forms.Form):
    fund = forms.ModelChoiceField(
        label="Fondo a arquear", queryset=TreasuryFund.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    counted_at = forms.DateTimeField(
        label="Fecha y hora del conteo",
        input_formats=("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"),
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M:%S",
            attrs={"type": "datetime-local", "step": "1", "class": "form-control"},
        ),
    )
    currency = forms.ChoiceField(
        choices=(("PEN", "Soles"), ("USD", "Dólares")),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    counted_amount = forms.DecimalField(
        label="Total físico contado", min_value=Decimal("0"), max_digits=14,
        decimal_places=2, widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    denominations = forms.JSONField(required=False, widget=forms.HiddenInput())
    notes = forms.CharField(
        label="Observación", required=False, max_length=500,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def __init__(self, *args, company_id=None, store_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fund"].queryset = TreasuryFund.objects.filter(
            company_id=company_id, store_id=store_id, active=True
        ).order_by("name")
        default = self.fields["fund"].queryset.filter(is_default=True).first()
        if default:
            self.fields["fund"].initial = default

    def clean_denominations(self):
        value = self.cleaned_data.get("denominations") or {}
        if not isinstance(value, dict):
            raise forms.ValidationError("El detalle de denominaciones no es válido.")
        normalized = {}
        for denomination, quantity in value.items():
            try:
                denomination_value = Decimal(str(denomination))
                quantity_value = int(quantity)
            except (ValueError, TypeError):
                raise forms.ValidationError("Las denominaciones contienen valores inválidos.")
            if denomination_value <= 0 or quantity_value < 0:
                raise forms.ValidationError("Las denominaciones y cantidades deben ser positivas.")
            if Decimal(str(quantity)) != Decimal(quantity_value):
                raise forms.ValidationError("La cantidad de cada denominación debe ser entera.")
            if quantity_value:
                normalized[str(denomination_value)] = quantity_value
        return normalized

    def clean_counted_at(self):
        value = self.cleaned_data["counted_at"]
        if value > timezone.now():
            raise forms.ValidationError("La fecha del conteo no puede estar en el futuro.")
        return value

    def clean(self):
        cleaned = super().clean()
        denominations = cleaned.get("denominations") or {}
        counted_amount = cleaned.get("counted_amount")
        if denominations and counted_amount is not None:
            denomination_total = sum(
                Decimal(value) * quantity for value, quantity in denominations.items()
            ).quantize(Decimal("0.01"))
            if denomination_total != counted_amount:
                self.add_error(
                    "counted_amount",
                    f"El total debe coincidir con las denominaciones ({denomination_total:.2f}).",
                )
        return cleaned


class CashSafeDepositConfirmationForm(forms.Form):
    deposit_id = forms.UUIDField(widget=forms.HiddenInput())
    operation_date = forms.DateField(
        label="Fecha efectiva del depósito",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    operation_reference = forms.CharField(
        label="N.º de operación o voucher", max_length=120,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    confirmation_notes = forms.CharField(
        label="Observación", required=False, max_length=500,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )

    def clean_operation_date(self):
        value = self.cleaned_data["operation_date"]
        if value > timezone.localdate():
            raise forms.ValidationError("La fecha del depósito no puede estar en el futuro.")
        return value


class CashSafeWithdrawalForm(forms.Form):
    fund = forms.ModelChoiceField(
        label="Origen del efectivo", queryset=TreasuryFund.objects.none(), required=False
    )
    destination_fund = forms.ModelChoiceField(
        label="Fondo destino", queryset=TreasuryFund.objects.none(), required=False
    )
    destination_register = forms.ModelChoiceField(
        label="Caja POS destino", queryset=PosRegister.objects.none(), required=False
    )
    movement_type = forms.ChoiceField(
        choices=[
            choice for choice in CashSafeMovement.MovementType.choices
            if choice[0] not in {
                CashSafeMovement.MovementType.CLOSING_DEPOSIT,
                CashSafeMovement.MovementType.MANUAL_INCOME,
                CashSafeMovement.MovementType.ADJUSTMENT,
            }
        ]
    )
    currency = forms.ChoiceField(choices=(("PEN", "Soles"), ("USD", "Dólares")))
    amount = forms.DecimalField(min_value=Decimal("0.01"), max_digits=14, decimal_places=2)
    recipient_name = forms.CharField(max_length=200, strip=True)
    destination = forms.CharField(max_length=200, required=False, strip=True)
    reference = forms.CharField(max_length=120, required=False, strip=True)
    notes = forms.CharField(max_length=500, required=False, strip=True)
    bank_account = forms.ModelChoiceField(queryset=BankAccount.objects.none(), required=False)
    supplier = forms.ModelChoiceField(
        label="Proveedor", queryset=Supplier.objects.none(), required=False
    )
    purchase_document = forms.ModelChoiceField(
        label="Documento de compra", queryset=PurchaseDocument.objects.none(), required=False
    )
    expense_category = forms.ModelChoiceField(
        label="Categoría del gasto", queryset=PurchaseCategory.objects.none(), required=False
    )
    supporting_document_number = forms.CharField(
        label="N.º de comprobante", max_length=80, required=False, strip=True
    )

    def __init__(self, *args, company_id=None, store_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_fund = None
        if company_id:
            self.fields["fund"].queryset = TreasuryFund.objects.filter(
                company_id=company_id, store_id=store_id, active=True
            ).order_by("name")
            self.fields["destination_fund"].queryset = TreasuryFund.objects.filter(
                company_id=company_id, store_id=store_id, active=True
            ).order_by("name")
            self.fields["destination_register"].queryset = PosRegister.objects.filter(
                company_id=company_id, store_id=store_id, active=True
            ).order_by("code", "name")
            default = self.fields["fund"].queryset.filter(is_default=True).first()
            if default:
                self.default_fund = default
                self.fields["fund"].initial = default
            self.fields["bank_account"].queryset = BankAccount.objects.filter(
                company_id=company_id, active=True
            ).select_related("bank")
            self.fields["supplier"].queryset = Supplier.objects.filter(
                company_id=company_id, active=True
            ).order_by("name")
            self.fields["expense_category"].queryset = PurchaseCategory.objects.filter(
                company_id=company_id, active=True
            ).order_by("name")
            documents = PurchaseDocument.objects.filter(company_id=company_id)
            if store_id:
                documents = documents.filter(store_id=store_id)
            self.fields["purchase_document"].queryset = documents.select_related(
                "supplier", "document_type"
            ).order_by("-issue_date", "-created_at")
        for name in (
            "fund", "destination_fund", "destination_register", "supplier",
            "purchase_document", "expense_category"
        ):
            self.fields[name].widget.attrs["class"] = "form-select"
        self.fields["supporting_document_number"].widget.attrs["class"] = "form-control"

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("fund"):
            if self.default_fund:
                cleaned["fund"] = self.default_fund
            else:
                self.add_error("fund", "Seleccione el fondo de origen.")
        if (
            cleaned.get("movement_type") == CashSafeMovement.MovementType.BANK_DEPOSIT
            and not cleaned.get("bank_account")
        ):
            self.add_error("bank_account", "Seleccione la cuenta bancaria de destino.")
        account = cleaned.get("bank_account")
        if account and cleaned.get("currency") != account.currency:
            self.add_error("bank_account", "La moneda debe coincidir con la cuenta bancaria.")
        if cleaned.get("movement_type") != CashSafeMovement.MovementType.BANK_DEPOSIT:
            cleaned["bank_account"] = None
        if cleaned.get("movement_type") == CashSafeMovement.MovementType.FUND_TRANSFER:
            destination_fund = cleaned.get("destination_fund")
            if not destination_fund:
                self.add_error("destination_fund", "Seleccione el fondo destino.")
            elif destination_fund == cleaned.get("fund"):
                self.add_error("destination_fund", "El fondo destino debe ser diferente al origen.")
        else:
            cleaned["destination_fund"] = None
        if cleaned.get("movement_type") == CashSafeMovement.MovementType.DRAWER_TRANSFER:
            if not cleaned.get("destination_register"):
                self.add_error("destination_register", "Seleccione la caja POS destino.")
        else:
            cleaned["destination_register"] = None
        document = cleaned.get("purchase_document")
        supplier = cleaned.get("supplier")
        if document and supplier and document.supplier_id != supplier.pk:
            self.add_error("purchase_document", "El documento no pertenece al proveedor seleccionado.")
        elif document and not supplier:
            cleaned["supplier"] = document.supplier
        if document and not cleaned.get("supporting_document_number"):
            cleaned["supporting_document_number"] = "-".join(
                part for part in (document.series, document.number) if part
            )
        if cleaned.get("movement_type") != CashSafeMovement.MovementType.CASH_PAYMENT:
            cleaned["supplier"] = None
            cleaned["purchase_document"] = None
            cleaned["expense_category"] = None
            cleaned["supporting_document_number"] = ""
        return cleaned


class CashSafeAttachmentForm(forms.Form):
    file = forms.FileField(
        label="Comprobante o evidencia",
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,.jpg,.jpeg,.png"}),
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        extension = Path(uploaded.name).suffix.lower()
        if extension not in {".pdf", ".jpg", ".jpeg", ".png"}:
            raise forms.ValidationError("Solo se permiten archivos PDF, JPG o PNG.")
        if uploaded.size > settings.TREASURY_ATTACHMENT_MAX_SIZE:
            raise forms.ValidationError("El archivo supera el tamaño máximo permitido de 5 MB.")
        allowed_types = {"application/pdf", "image/jpeg", "image/png"}
        if uploaded.content_type not in allowed_types:
            raise forms.ValidationError("El tipo de archivo no es válido.")
        signature = uploaded.read(8)
        uploaded.seek(0)
        signatures = {
            ".pdf": (b"%PDF-",),
            ".jpg": (b"\xff\xd8\xff",),
            ".jpeg": (b"\xff\xd8\xff",),
            ".png": (b"\x89PNG\r\n\x1a\n",),
        }
        if not any(signature.startswith(prefix) for prefix in signatures[extension]):
            raise forms.ValidationError("El contenido del archivo no coincide con su extensión.")
        return uploaded


class CashSafeIncomeForm(forms.Form):
    fund = forms.ModelChoiceField(
        label="Fondo de destino", queryset=TreasuryFund.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    currency = forms.ChoiceField(
        choices=(("PEN", "Soles"), ("USD", "Dólares")),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    amount = forms.DecimalField(
        label="Importe", min_value=Decimal("0.01"), max_digits=14, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    source_name = forms.CharField(
        label="Entregado por / procedencia", max_length=200,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    reference = forms.CharField(
        label="Documento o referencia", required=False, max_length=120,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    notes = forms.CharField(
        label="Motivo u observación", max_length=500,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def __init__(self, *args, company_id=None, store_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fund"].queryset = TreasuryFund.objects.filter(
            company_id=company_id, store_id=store_id, active=True
        ).order_by("name")
        default = self.fields["fund"].queryset.filter(is_default=True).first()
        if default:
            self.fields["fund"].initial = default


class TreasuryFundForm(forms.ModelForm):
    class Meta:
        model = TreasuryFund
        fields = ("code", "name", "fund_type", "notes", "active")

    def __init__(self, *args, company_id=None, store_id=None, **kwargs):
        self.company_id = company_id
        self.store_id = store_id
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "form-check-input" if isinstance(field.widget, forms.CheckboxInput)
                else "form-select" if isinstance(field.widget, forms.Select)
                else "form-control"
            )
        self.fields["code"].label = "Código"
        self.fields["name"].label = "Nombre del fondo"
        self.fields["fund_type"].label = "Tipo"

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        if self.store_id and TreasuryFund.objects.filter(
            store_id=self.store_id, code=code
        ).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe un fondo con este código en la tienda.")
        return code


class BankAccountForm(forms.ModelForm):
    bank_name = forms.CharField(label="Banco", max_length=150)

    class Meta:
        model = BankAccount
        fields = (
            "name", "account_type", "currency", "account_number", "cci",
            "accounting_account", "max_transfer_amount", "use_for_payments",
            "is_detracciones", "opening_balance", "opening_balance_date", "active",
        )
        widgets = {"opening_balance_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, company_id=None, **kwargs):
        self.company_id = company_id
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.bank_id:
            self.fields["bank_name"].initial = self.instance.bank.name
        for field in self.fields.values():
            css_class = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else (
                "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            )
            field.widget.attrs["class"] = css_class
        self.fields["name"].label = "Alias de la cuenta"
        self.fields["account_number"].label = "Número de cuenta"
        self.fields["accounting_account"].label = "Cuenta contable"
        self.fields["max_transfer_amount"].label = "Límite máximo por transferencia"
        self.fields["use_for_payments"].label = "Usar para egresos"
        self.fields["is_detracciones"].label = "Cuenta de detracciones"
        self.fields["opening_balance"].label = "Saldo inicial"
        self.fields["opening_balance_date"].label = "Fecha del saldo inicial"

    def clean(self):
        cleaned = super().clean()
        number = (cleaned.get("account_number") or "").strip()
        if self.company_id and number:
            duplicated = BankAccount.objects.filter(
                company_id=self.company_id, account_number=number
            ).exclude(pk=self.instance.pk)
            if duplicated.exists():
                self.add_error("account_number", "Ya existe esta cuenta en la empresa.")
        if self.instance.pk and (
            self.instance.movements.exists() or self.instance.statements.exists()
        ):
            original = BankAccount.objects.get(pk=self.instance.pk)
            if cleaned.get("opening_balance") != original.opening_balance:
                self.add_error(
                    "opening_balance",
                    "El saldo inicial no puede modificarse cuando la cuenta ya tiene actividad.",
                )
            if cleaned.get("opening_balance_date") != original.opening_balance_date:
                self.add_error(
                    "opening_balance_date",
                    "La fecha inicial no puede modificarse cuando la cuenta ya tiene actividad.",
                )
            if cleaned.get("currency") != original.currency:
                self.add_error(
                    "currency", "La moneda no puede modificarse cuando la cuenta ya tiene actividad."
                )
            if number != original.account_number:
                self.add_error(
                    "account_number",
                    "El número de cuenta no puede modificarse cuando ya existe actividad.",
                )
            if (cleaned.get("bank_name") or "").strip() != original.bank.name:
                self.add_error(
                    "bank_name", "El banco no puede modificarse cuando la cuenta ya tiene actividad."
                )
        return cleaned

    def save(self, commit=True):
        account = super().save(commit=False)
        bank, _ = Bank.objects.get_or_create(
            company_id=self.company_id,
            name=self.cleaned_data["bank_name"].strip(),
        )
        account.company_id = self.company_id
        account.bank = bank
        if commit:
            account.full_clean()
            account.save()
        return account


class BankMovementForm(forms.ModelForm):
    class Meta:
        model = BankMovement
        fields = (
            "account", "destination_account", "direction", "movement_type", "amount",
            "operation_date", "reference", "description",
        )
        widgets = {"operation_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, company_id=None, fixed_direction=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = BankAccount.objects.filter(
            company_id=company_id, active=True
        ).select_related("bank")
        self.fields["destination_account"].queryset = BankAccount.objects.filter(
            company_id=company_id, active=True
        ).select_related("bank")
        self.fields["destination_account"].required = False
        self.fields["destination_account"].label = "Cuenta destino"
        movement_type_choices = [
            choice for choice in BankMovement.MovementType.choices
            if choice[0] != BankMovement.MovementType.SAFE_DEPOSIT
        ]
        if fixed_direction == BankMovement.Direction.IN:
            allowed = {
                BankMovement.MovementType.RECEIPT,
                BankMovement.MovementType.INTEREST,
                BankMovement.MovementType.ADJUSTMENT,
            }
            movement_type_choices = [c for c in movement_type_choices if c[0] in allowed]
        elif fixed_direction == BankMovement.Direction.OUT:
            allowed = {
                BankMovement.MovementType.PAYMENT,
                BankMovement.MovementType.TRANSFER,
                BankMovement.MovementType.FEE,
                BankMovement.MovementType.ADJUSTMENT,
            }
            movement_type_choices = [c for c in movement_type_choices if c[0] in allowed]
        if fixed_direction != BankMovement.Direction.OUT:
            self.fields["destination_account"].widget = forms.HiddenInput()
        self.fields["movement_type"].choices = movement_type_choices
        if fixed_direction:
            self.fields["direction"].initial = fixed_direction
            self.fields["direction"].widget = forms.HiddenInput()
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            )

    def clean(self):
        cleaned = super().clean()
        account = cleaned.get("account")
        destination = cleaned.get("destination_account")
        is_transfer = (
            cleaned.get("movement_type") == BankMovement.MovementType.TRANSFER
            and cleaned.get("direction") == BankMovement.Direction.OUT
        )
        if is_transfer and not destination:
            self.add_error("destination_account", "Seleccione la cuenta bancaria destino.")
        elif destination:
            if not is_transfer:
                cleaned["destination_account"] = None
            elif destination == account:
                self.add_error("destination_account", "La cuenta destino debe ser diferente al origen.")
            elif account and destination.currency != account.currency:
                self.add_error("destination_account", "Las cuentas deben utilizar la misma moneda.")
        return cleaned


class BankStatementImportForm(forms.ModelForm):
    statement_file = forms.FileField(
        label="Extracto bancario (CSV o XLSX)",
        help_text="Columnas: fecha, descripción, referencia y cargo/abono; o fecha, descripción, referencia y monto.",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,.xlsx"}),
    )

    class Meta:
        model = BankStatement
        fields = ("account", "date_from", "date_to", "opening_balance", "closing_balance")
        widgets = {
            "date_from": forms.DateInput(attrs={"type": "date"}),
            "date_to": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, company_id=None, **kwargs):
        self.company_id = company_id
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = BankAccount.objects.filter(
            company_id=company_id, active=True
        ).select_related("bank")
        self.fields["date_from"].label = "Desde"
        self.fields["date_to"].label = "Hasta"
        self.fields["opening_balance"].label = "Saldo inicial del extracto"
        self.fields["closing_balance"].label = "Saldo final del extracto"
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            )

    def clean(self):
        cleaned = super().clean()
        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        account = cleaned.get("account")
        if date_from and date_to and date_to < date_from:
            self.add_error("date_to", "La fecha final no puede ser anterior a la inicial.")
        if account and date_from and date_from < account.opening_balance_date:
            self.add_error(
                "date_from", "El periodo no puede comenzar antes de la fecha inicial de la cuenta."
            )
        if account and date_from and date_to and BankStatement.objects.filter(
            account=account, date_from__lte=date_to, date_to__gte=date_from
        ).exists():
            self.add_error("date_to", "El periodo se superpone con otra conciliación de la cuenta.")
        return cleaned
