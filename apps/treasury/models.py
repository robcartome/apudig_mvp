import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TimeStampedModel


def cash_safe_attachment_upload_to(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"treasury/cash-safe/{instance.movement_id}/{uuid.uuid4().hex}{extension}"


class Bank(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE, related_name="treasury_banks"
    )
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=30, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "treasury_banks"
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=("company", "name"), name="uniq_treasury_bank_name")
        ]

    def __str__(self):
        return self.name


class BankAccount(TimeStampedModel):
    class AccountType(models.TextChoices):
        CHECKING = "CHECKING", "Cuenta corriente"
        SAVINGS = "SAVINGS", "Cuenta de ahorros"
        OTHER = "OTHER", "Otra"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE, related_name="treasury_bank_accounts"
    )
    bank = models.ForeignKey(Bank, on_delete=models.PROTECT, related_name="accounts")
    name = models.CharField(max_length=150)
    account_type = models.CharField(
        max_length=15, choices=AccountType.choices, default=AccountType.CHECKING
    )
    currency = models.CharField(
        max_length=3, choices=(("PEN", "Soles"), ("USD", "Dólares")), default="PEN"
    )
    account_number = models.CharField(max_length=50)
    cci = models.CharField(max_length=30, blank=True)
    accounting_account = models.CharField(max_length=30, blank=True)
    use_for_payments = models.BooleanField(default=True)
    is_detracciones = models.BooleanField(default=False)
    max_transfer_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="Cero significa sin límite configurado.",
    )
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    opening_balance_date = models.DateField()
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "treasury_bank_accounts"
        ordering = ("bank__name", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("company", "account_number"), name="uniq_treasury_bank_account_number"
            ),
            models.CheckConstraint(
                condition=models.Q(opening_balance__gte=0), name="treasury_bank_opening_gte_zero"
            ),
            models.CheckConstraint(
                condition=models.Q(max_transfer_amount__gte=0),
                name="treasury_bank_transfer_limit_gte_zero",
            ),
        ]

    @property
    def masked_number(self):
        clean = self.account_number.replace(" ", "")
        return f"•••• {clean[-4:]}" if len(clean) > 4 else clean

    def clean(self):
        if (
            self.bank_id and self.company_id
            and str(self.bank.company_id) != str(self.company_id)
        ):
            raise ValidationError({"bank": "El banco debe pertenecer a la empresa."})

    def __str__(self):
        return f"{self.bank.name} · {self.name} · {self.masked_number}"


class BankMovement(TimeStampedModel):
    class Direction(models.TextChoices):
        IN = "IN", "Ingreso"
        OUT = "OUT", "Egreso"

    class MovementType(models.TextChoices):
        SAFE_DEPOSIT = "SAFE_DEPOSIT", "Depósito desde caja fuerte"
        RECEIPT = "RECEIPT", "Ingreso"
        PAYMENT = "PAYMENT", "Pago"
        TRANSFER = "TRANSFER", "Transferencia"
        FEE = "FEE", "Comisión bancaria"
        INTEREST = "INTEREST", "Interés"
        ADJUSTMENT = "ADJUSTMENT", "Ajuste"

    class Status(models.TextChoices):
        POSTED = "POSTED", "Confirmado"
        VOIDED = "VOIDED", "Anulado"
        REVERSED = "REVERSED", "Revertido"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.PROTECT, related_name="treasury_bank_movements"
    )
    account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name="movements")
    destination_account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, null=True, blank=True,
        related_name="incoming_transfer_requests",
    )
    transfer_source = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True,
        related_name="transfer_destination_movement",
    )
    sequence_number = models.PositiveBigIntegerField(default=0)
    movement_number = models.CharField(max_length=30)
    direction = models.CharField(max_length=3, choices=Direction.choices)
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    operation_date = models.DateField()
    reference = models.CharField(max_length=120, blank=True)
    description = models.CharField(max_length=500)
    source_type = models.CharField(max_length=40, blank=True)
    source_id = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.POSTED)
    safe_movement = models.OneToOneField(
        "CashSafeMovement", on_delete=models.PROTECT, null=True, blank=True,
        related_name="bank_movement",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="created_treasury_bank_movements",
    )
    reversed_movement = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True,
        related_name="reversal",
    )
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversal_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = "treasury_bank_movements"
        ordering = ("-operation_date", "-created_at")
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="treasury_bank_movement_gt_zero"),
            models.UniqueConstraint(fields=("company", "movement_number"), name="uniq_treasury_bank_movement_number"),
            models.UniqueConstraint(
                fields=("company", "source_type", "source_id"),
                condition=~models.Q(source_id=""),
                name="uniq_treasury_bank_movement_source",
            ),
        ]

    def clean(self):
        errors = {}
        if (
            self.account_id and self.company_id
            and str(self.account.company_id) != str(self.company_id)
        ):
            errors["account"] = "La cuenta debe pertenecer a la empresa."
        if self.destination_account_id and self.company_id:
            if str(self.destination_account.company_id) != str(self.company_id):
                errors["destination_account"] = "La cuenta destino debe pertenecer a la empresa."
            elif self.destination_account_id == self.account_id:
                errors["destination_account"] = "La cuenta destino debe ser diferente al origen."
            elif self.destination_account.currency != self.account.currency:
                errors["destination_account"] = "Las cuentas de una transferencia deben usar la misma moneda."
        if (
            self.movement_type == self.MovementType.TRANSFER
            and self.direction == self.Direction.OUT and not self.destination_account_id
        ):
            errors["destination_account"] = "Seleccione la cuenta bancaria destino."
        if self.transfer_source_id and (
            self.direction != self.Direction.IN
            or self.movement_type != self.MovementType.TRANSFER
        ):
            errors["transfer_source"] = "La contrapartida debe ser un ingreso por transferencia."
        if errors:
            raise ValidationError(errors)


class BankStatement(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "En conciliación"
        RECONCILED = "RECONCILED", "Conciliado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.PROTECT, related_name="bank_statements"
    )
    account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name="statements"
    )
    date_from = models.DateField()
    date_to = models.DateField()
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    source_filename = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="created_bank_statements",
    )
    reconciled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reconciled_bank_statements",
    )
    reconciled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "treasury_bank_statements"
        ordering = ("-date_to", "-created_at")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(date_to__gte=models.F("date_from")),
                name="treasury_statement_valid_range",
            ),
            models.UniqueConstraint(
                fields=("account", "date_from", "date_to"),
                name="uniq_treasury_statement_period",
            ),
        ]

    def clean(self):
        if (
            self.account_id and self.company_id
            and str(self.account.company_id) != str(self.company_id)
        ):
            raise ValidationError({"account": "La cuenta debe pertenecer a la empresa."})


class BankStatementLine(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    statement = models.ForeignKey(
        BankStatement, on_delete=models.CASCADE, related_name="lines"
    )
    transaction_date = models.DateField()
    direction = models.CharField(max_length=3, choices=BankMovement.Direction.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reference = models.CharField(max_length=120, blank=True)
    description = models.CharField(max_length=500)
    fingerprint = models.CharField(max_length=64)

    class Meta:
        db_table = "treasury_bank_statement_lines"
        ordering = ("transaction_date", "created_at")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="treasury_statement_line_amount_gt_zero"
            ),
            models.UniqueConstraint(
                fields=("statement", "fingerprint"),
                name="uniq_treasury_statement_line_fingerprint",
            ),
        ]


class BankReconciliationMatch(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    statement_line = models.ForeignKey(
        BankStatementLine, on_delete=models.CASCADE, related_name="reconciliation_matches"
    )
    bank_movement = models.OneToOneField(
        BankMovement, on_delete=models.PROTECT, related_name="reconciliation_match"
    )
    matched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="bank_reconciliation_matches",
    )

    class Meta:
        db_table = "treasury_bank_reconciliation_matches"
        constraints = [
            models.UniqueConstraint(
                fields=("statement_line", "bank_movement"),
                name="uniq_treasury_reconciliation_line_movement",
            )
        ]


class TreasuryFund(TimeStampedModel):
    """Ubicación física o fondo responsable de custodiar efectivo."""

    class FundType(models.TextChoices):
        SAFE = "SAFE", "Caja fuerte"
        PETTY_CASH = "PETTY_CASH", "Caja chica"
        ADMINISTRATIVE = "ADMINISTRATIVE", "Fondo administrativo"
        OTHER = "OTHER", "Otro fondo"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE, related_name="treasury_funds"
    )
    store = models.ForeignKey(
        "companies.Store", on_delete=models.CASCADE, related_name="treasury_funds"
    )
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    fund_type = models.CharField(
        max_length=20, choices=FundType.choices, default=FundType.SAFE
    )
    is_default = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "treasury_funds"
        ordering = ("store__name", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("store", "code"), name="uniq_treasury_fund_store_code"
            ),
            models.UniqueConstraint(
                fields=("store",), condition=models.Q(is_default=True),
                name="uniq_treasury_default_fund_per_store",
            ),
        ]

    def clean(self):
        if (
            self.store_id and self.company_id
            and str(self.store.company_id) != str(self.company_id)
        ):
            raise ValidationError({"store": "La tienda debe pertenecer a la empresa."})
        if self.is_default and not self.active:
            raise ValidationError({"active": "El fondo principal debe permanecer activo."})

    def __str__(self):
        return self.name


class CashSafeMovement(TimeStampedModel):
    class Direction(models.TextChoices):
        IN = "IN", "Ingreso"
        OUT = "OUT", "Salida"

    class MovementType(models.TextChoices):
        CLOSING_DEPOSIT = "CLOSING_DEPOSIT", "Guardado desde cierre de caja"
        MANUAL_INCOME = "MANUAL_INCOME", "Ingreso manual o reposición"
        BANK_DEPOSIT = "BANK_DEPOSIT", "Entrega para depósito bancario"
        OWNER_HANDOVER = "OWNER_HANDOVER", "Entrega a dueño o administrador"
        CASH_PAYMENT = "CASH_PAYMENT", "Pago en efectivo"
        DRAWER_TRANSFER = "DRAWER_TRANSFER", "Transferencia a gaveta"
        FUND_TRANSFER = "FUND_TRANSFER", "Transferencia entre fondos"
        ADJUSTMENT = "ADJUSTMENT", "Ajuste autorizado"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente de aprobación"
        POSTED = "POSTED", "Confirmado"
        REJECTED = "REJECTED", "Rechazado"
        REVERSED = "REVERSED", "Revertido"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.PROTECT, related_name="cash_safe_movements"
    )
    store = models.ForeignKey(
        "companies.Store", on_delete=models.PROTECT, related_name="cash_safe_movements"
    )
    fund = models.ForeignKey(
        TreasuryFund, on_delete=models.PROTECT, related_name="cash_movements"
    )
    destination_fund = models.ForeignKey(
        TreasuryFund, on_delete=models.PROTECT, null=True, blank=True,
        related_name="incoming_transfer_requests",
    )
    destination_register = models.ForeignKey(
        "pos.PosRegister", on_delete=models.PROTECT, null=True, blank=True,
        related_name="cash_safe_transfers_received",
    )
    transfer_source = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True,
        related_name="transfer_destination_movement",
    )
    cash_session = models.ForeignKey(
        "pos.CashSession", on_delete=models.PROTECT, null=True, blank=True,
        related_name="safe_movements",
    )
    bank_account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, null=True, blank=True,
        related_name="cash_safe_movements",
    )
    supplier = models.ForeignKey(
        "partners.Supplier", on_delete=models.PROTECT, null=True, blank=True,
        related_name="cash_safe_movements",
    )
    purchase_document = models.ForeignKey(
        "purchases.PurchaseDocument", on_delete=models.PROTECT, null=True, blank=True,
        related_name="cash_safe_movements",
    )
    expense_category = models.ForeignKey(
        "purchases.PurchaseCategory", on_delete=models.PROTECT, null=True, blank=True,
        related_name="cash_safe_movements",
    )
    supporting_document_number = models.CharField(max_length=80, blank=True)
    direction = models.CharField(max_length=3, choices=Direction.choices)
    movement_type = models.CharField(max_length=30, choices=MovementType.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(
        max_length=3, choices=(("PEN", "Soles"), ("USD", "Dólares")), default="PEN"
    )
    sequence_number = models.PositiveBigIntegerField(default=0)
    movement_number = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.POSTED)
    recipient_name = models.CharField(max_length=200, blank=True)
    destination = models.CharField(max_length=200, blank=True)
    reference = models.CharField(max_length=120, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="created_cash_safe_movements",
    )
    authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="authorized_cash_safe_movements",
    )
    authorized_at = models.DateTimeField(null=True, blank=True)
    reversed_movement = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True,
        related_name="reversal",
    )
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversal_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = "pos_cash_safe_movements"
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="cash_safe_movement_amount_gt_zero"
            ),
            models.UniqueConstraint(
                fields=("company", "movement_number"),
                condition=~models.Q(movement_number=""),
                name="uniq_cash_safe_movement_number",
            ),
        ]

    def clean(self):
        errors = {}
        if (
            self.company_id and self.store_id
            and str(self.store.company_id) != str(self.company_id)
        ):
            errors["store"] = "La tienda debe pertenecer a la empresa."
        if self.fund_id and (
            str(self.fund.company_id) != str(self.company_id)
            or str(self.fund.store_id) != str(self.store_id)
        ):
            errors["fund"] = "El fondo debe pertenecer a la empresa y tienda."
        if self.destination_fund_id:
            if (
                str(self.destination_fund.company_id) != str(self.company_id)
                or str(self.destination_fund.store_id) != str(self.store_id)
            ):
                errors["destination_fund"] = "El fondo destino debe pertenecer a la tienda."
            elif self.destination_fund_id == self.fund_id:
                errors["destination_fund"] = "El fondo destino debe ser diferente al origen."
        if self.destination_register_id and (
            str(self.destination_register.company_id) != str(self.company_id)
            or str(self.destination_register.store_id) != str(self.store_id)
        ):
            errors["destination_register"] = "La caja destino debe pertenecer a la empresa y tienda."
        if (
            self.movement_type == self.MovementType.DRAWER_TRANSFER
            and not self.destination_register_id
        ):
            errors["destination_register"] = "Seleccione la caja POS destino."
        if (
            self.movement_type == self.MovementType.FUND_TRANSFER
            and self.direction == self.Direction.OUT and not self.destination_fund_id
        ):
            errors["destination_fund"] = "Seleccione el fondo destino de la transferencia."
        if self.transfer_source_id and (
            self.direction != self.Direction.IN
            or self.movement_type != self.MovementType.FUND_TRANSFER
        ):
            errors["transfer_source"] = "La contrapartida debe ser un ingreso por transferencia."
        if self.supplier_id and str(self.supplier.company_id) != str(self.company_id):
            errors["supplier"] = "El proveedor debe pertenecer a la empresa."
        if self.purchase_document_id:
            if (
                str(self.purchase_document.company_id) != str(self.company_id)
                or str(self.purchase_document.store_id) != str(self.store_id)
            ):
                errors["purchase_document"] = "El documento debe pertenecer a la empresa y tienda."
            elif self.supplier_id and self.purchase_document.supplier_id != self.supplier_id:
                errors["purchase_document"] = "El documento no pertenece al proveedor seleccionado."
        if self.expense_category_id and str(self.expense_category.company_id) != str(self.company_id):
            errors["expense_category"] = "La categoría debe pertenecer a la empresa."
        if errors:
            raise ValidationError(errors)


class CashSafeCount(TimeStampedModel):
    """Snapshot físico del efectivo custodiado en una tienda."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente de revisión"
        CLOSED = "CLOSED", "Cerrado"
        REJECTED = "REJECTED", "Rechazado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.PROTECT, related_name="cash_safe_counts"
    )
    store = models.ForeignKey(
        "companies.Store", on_delete=models.PROTECT, related_name="cash_safe_counts"
    )
    fund = models.ForeignKey(
        TreasuryFund, on_delete=models.PROTECT, related_name="cash_counts"
    )
    sequence_number = models.PositiveBigIntegerField()
    count_number = models.CharField(max_length=30)
    counted_at = models.DateTimeField()
    currency = models.CharField(
        max_length=3, choices=(("PEN", "Soles"), ("USD", "Dólares")), default="PEN"
    )
    theoretical_amount = models.DecimalField(max_digits=14, decimal_places=2)
    counted_amount = models.DecimalField(max_digits=14, decimal_places=2)
    difference = models.DecimalField(max_digits=14, decimal_places=2)
    denominations = models.JSONField(default=dict, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    counted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="performed_cash_safe_counts",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_cash_safe_counts",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.CharField(max_length=500, blank=True)
    adjustment_movement = models.OneToOneField(
        CashSafeMovement, on_delete=models.PROTECT, null=True, blank=True,
        related_name="cash_safe_count",
    )

    class Meta:
        db_table = "treasury_cash_safe_counts"
        ordering = ("-counted_at", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("company", "count_number"), name="uniq_cash_safe_count_number"
            ),
            models.CheckConstraint(
                condition=models.Q(counted_amount__gte=0), name="cash_safe_count_amount_gte_zero"
            ),
        ]

    def clean(self):
        if (
            self.company_id and self.store_id
            and str(self.store.company_id) != str(self.company_id)
        ):
            raise ValidationError({"store": "La tienda debe pertenecer a la empresa."})
        if self.fund_id and (
            str(self.fund.company_id) != str(self.company_id)
            or str(self.fund.store_id) != str(self.store_id)
        ):
            raise ValidationError({"fund": "El fondo debe pertenecer a la empresa y tienda."})


class CashSafeDeposit(TimeStampedModel):
    """Custodia del efectivo retirado de caja fuerte hasta su depósito real."""

    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "Pendiente de entrega"
        IN_TRANSIT = "IN_TRANSIT", "En tránsito"
        DEPOSITED = "DEPOSITED", "Depositado"
        CANCELLED = "CANCELLED", "Cancelado"
        REVERSED = "REVERSED", "Revertido"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cash_movement = models.OneToOneField(
        CashSafeMovement, on_delete=models.PROTECT, related_name="deposit_tracking"
    )
    account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name="cash_safe_deposits"
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.REQUESTED
    )
    handed_over_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="handed_over_cash_safe_deposits",
    )
    handed_over_at = models.DateTimeField(null=True, blank=True)
    deposited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="confirmed_cash_safe_deposits",
    )
    deposited_at = models.DateTimeField(null=True, blank=True)
    operation_date = models.DateField(null=True, blank=True)
    operation_reference = models.CharField(max_length=120, blank=True)
    confirmation_notes = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = "treasury_cash_safe_deposits"
        ordering = ("-created_at",)


class CashSafeMovementAttachment(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    movement = models.ForeignKey(
        CashSafeMovement, on_delete=models.CASCADE, related_name="attachments"
    )
    file = models.FileField(upload_to=cash_safe_attachment_upload_to, max_length=500)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.PositiveBigIntegerField()
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="cash_safe_attachments",
    )

    class Meta:
        db_table = "treasury_cash_safe_movement_attachments"
        ordering = ("created_at",)
