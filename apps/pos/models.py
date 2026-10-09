import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.managers import CompanyScopedManager
from apps.core.models import TimeStampedModel


class PosRegister(TimeStampedModel):
    """Caja logica o fisica desde la que se procesan ventas POS."""

    objects = CompanyScopedManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE, related_name="pos_registers"
    )
    store = models.ForeignKey(
        "companies.Store", on_delete=models.CASCADE, related_name="pos_registers"
    )
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=120)
    active = models.BooleanField(default=True)
    default_warehouse = models.ForeignKey(
        "inventory.Warehouse", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pos_registers",
    )
    default_price_list = models.ForeignKey(
        "inventory.PriceList", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pos_registers",
    )
    default_customer = models.ForeignKey(
        "partners.Customer", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pos_registers",
    )
    default_document_type = models.ForeignKey(
        "partners.DocumentType", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pos_registers",
    )
    ticket_series = models.CharField(max_length=10, default="T")
    current_ticket_number = models.PositiveBigIntegerField(default=0, editable=False)
    current_session_number = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        db_table = "pos_registers"
        ordering = ("store_id", "code")
        constraints = [
            models.UniqueConstraint(
                fields=("company", "store", "code"), name="uniq_pos_register_code"
            ),
        ]

    def clean(self):
        errors = {}
        if self.store_id and self.company_id and self.store.company_id != self.company_id:
            errors["store"] = "La caja y la sucursal deben pertenecer a la misma empresa."
        if self.default_warehouse_id and self.default_warehouse.store_id != self.store_id:
            errors["default_warehouse"] = "El almacen predeterminado debe pertenecer a la sucursal."
        if self.default_price_list_id and self.default_price_list.company_id != self.company_id:
            errors["default_price_list"] = "La lista de precios debe pertenecer a la empresa."
        if self.default_customer_id and self.default_customer.company_id != self.company_id:
            errors["default_customer"] = "El cliente predeterminado debe pertenecer a la empresa."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.store} / {self.code} - {self.name}"


class CashSession(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Abierta"
        CLOSED = "CLOSED", "Cerrada"

    objects = CompanyScopedManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_number = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, choices=(("PEN", "Soles"), ("USD", "Dolares")), default="PEN")
    register = models.ForeignKey(
        PosRegister, on_delete=models.PROTECT, related_name="cash_sessions"
    )
    company = models.ForeignKey(
        "companies.Company", on_delete=models.PROTECT, related_name="cash_sessions"
    )
    store = models.ForeignKey(
        "companies.Store", on_delete=models.PROTECT, related_name="cash_sessions"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="opened_cash_sessions",
    )
    opened_at = models.DateTimeField(default=timezone.now)
    opening_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    opening_note = models.CharField(max_length=500, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="closed_cash_sessions",
    )
    difference_authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="authorized_cash_session_differences",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    expected_cash_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    counted_cash_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cash_difference = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    next_opening_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    safe_deposit_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    bank_deposit_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    bank_deposit_destination = models.CharField(max_length=200, blank=True)
    closing_note = models.CharField(max_length=500, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "pos_cash_sessions"
        ordering = ("-opened_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("register",), condition=models.Q(status="OPEN"),
                name="uniq_open_cash_session_per_register",
            ),
            models.UniqueConstraint(
                fields=("register", "session_number"), name="uniq_cash_session_number_per_register"
            ),
            models.CheckConstraint(
                condition=models.Q(opening_total__gte=0), name="cash_session_opening_gte_zero"
            ),
            models.CheckConstraint(
                condition=models.Q(next_opening_total__isnull=True)
                | models.Q(next_opening_total__gte=0),
                name="cash_session_next_opening_gte_zero",
            ),
        ]

    def clean(self):
        errors = {}
        if self.register_id:
            if self.company_id != self.register.company_id:
                errors["company"] = "La sesion debe pertenecer a la empresa de la caja."
            if self.store_id != self.register.store_id:
                errors["store"] = "La sesion debe pertenecer a la sucursal de la caja."
        if self.currency not in {"PEN", "USD"}:
            errors["currency"] = "La moneda de la sesion debe ser S/. o $."
        if self.status == self.Status.CLOSED and (not self.closed_at or not self.closed_by_id):
            errors["status"] = "Una sesion cerrada requiere fecha y responsable de cierre."
        if (
            self.status == self.Status.CLOSED
            and self.cash_difference not in (None, Decimal("0.00"))
            and not self.difference_authorized_by_id
        ):
            errors["difference_authorized_by"] = (
                "Una diferencia de caja requiere autorizacion."
            )
        if (
            self.status == self.Status.CLOSED
            and self.cash_difference not in (None, Decimal("0.00"))
            and not (self.closing_note or "").strip()
        ):
            errors["closing_note"] = "Una diferencia de caja requiere una observacion."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.register} / Sesion {self.session_number}"


class CashSafeMovement(TimeStampedModel):
    class Direction(models.TextChoices):
        IN = "IN", "Ingreso"
        OUT = "OUT", "Salida"

    class MovementType(models.TextChoices):
        CLOSING_DEPOSIT = "CLOSING_DEPOSIT", "Guardado desde cierre de caja"
        BANK_DEPOSIT = "BANK_DEPOSIT", "Entrega para depósito bancario"
        OWNER_HANDOVER = "OWNER_HANDOVER", "Entrega a dueño o administrador"
        CASH_PAYMENT = "CASH_PAYMENT", "Pago en efectivo"
        DRAWER_TRANSFER = "DRAWER_TRANSFER", "Transferencia a gaveta"
        ADJUSTMENT = "ADJUSTMENT", "Ajuste autorizado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.PROTECT, related_name="cash_safe_movements"
    )
    store = models.ForeignKey(
        "companies.Store", on_delete=models.PROTECT, related_name="cash_safe_movements"
    )
    cash_session = models.ForeignKey(
        CashSession, on_delete=models.PROTECT, null=True, blank=True,
        related_name="safe_movements",
    )
    direction = models.CharField(max_length=3, choices=Direction.choices)
    movement_type = models.CharField(max_length=30, choices=MovementType.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, choices=(("PEN", "Soles"), ("USD", "Dólares")), default="PEN")
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

    class Meta:
        db_table = "pos_cash_safe_movements"
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="cash_safe_movement_amount_gt_zero"
            ),
        ]


class CashDenominationCount(models.Model):
    class Phase(models.TextChoices):
        OPENING = "OPENING", "Apertura"
        CLOSING = "CLOSING", "Cierre"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cash_session = models.ForeignKey(
        CashSession, on_delete=models.CASCADE, related_name="denomination_counts"
    )
    phase = models.CharField(max_length=10, choices=Phase.choices)
    denomination = models.DecimalField(max_digits=14, decimal_places=2)
    quantity = models.PositiveIntegerField()
    total = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        db_table = "pos_cash_denomination_counts"
        ordering = ("phase", "-denomination")
        constraints = [
            models.UniqueConstraint(
                fields=("cash_session", "phase", "denomination"),
                name="uniq_cash_denomination_per_phase",
            ),
            models.CheckConstraint(
                condition=models.Q(denomination__gt=0), name="cash_denomination_gt_zero"
            ),
            models.CheckConstraint(
                condition=models.Q(total__gte=0), name="cash_denomination_total_gte_zero"
            ),
        ]

    def clean(self):
        expected = (Decimal(self.denomination) * self.quantity).quantize(Decimal("0.01"))
        if self.total != expected:
            raise ValidationError({"total": "El total no coincide con denominacion por cantidad."})


class CashMovement(TimeStampedModel):
    class MovementType(models.TextChoices):
        PAY_IN = "PAY_IN", "Ingreso"
        PAY_OUT = "PAY_OUT", "Egreso"
        WITHDRAWAL = "WITHDRAWAL", "Retiro"
        DEPOSIT = "DEPOSIT", "Deposito"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cash_session = models.ForeignKey(
        CashSession, on_delete=models.PROTECT, related_name="cash_movements"
    )
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    means_of_payment = models.ForeignKey(
        "sales.MeansOfPayment", on_delete=models.PROTECT, null=True, blank=True,
        related_name="cash_movements",
    )
    operation_reference = models.CharField(max_length=120, blank=True)
    reason_code = models.CharField(max_length=40, blank=True)
    description = models.CharField(max_length=500)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="created_pos_cash_movements",
    )
    authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="authorized_pos_cash_movements",
    )

    class Meta:
        db_table = "pos_cash_movements"
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="cash_movement_amount_gt_zero"
            ),
        ]

    def clean(self):
        errors = {}
        if self.cash_session_id and self.cash_session.status != CashSession.Status.OPEN:
            errors["cash_session"] = "No se puede modificar una sesion de caja cerrada."
        if (
            self.movement_type in (self.MovementType.WITHDRAWAL, self.MovementType.DEPOSIT)
            and not self.authorized_by_id
        ):
            errors["authorized_by"] = "Los retiros y depositos requieren autorizacion."
        if (
            self.cash_session_id
            and self.means_of_payment_id
            and self.means_of_payment.company_id != self.cash_session.company_id
        ):
            errors["means_of_payment"] = "El medio de pago debe pertenecer a la empresa de la caja."
        if errors:
            raise ValidationError(errors)


class PosTransaction(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Borrador"
        PAYMENT_PENDING = "PAYMENT_PENDING", "Pago pendiente"
        PROCESSING = "PROCESSING", "Procesando"
        COMPLETED = "COMPLETED", "Completada"
        CANCELLED = "CANCELLED", "Cancelada"
        FAILED = "FAILED", "Fallida"

    class BillingStatus(models.TextChoices):
        NOT_REQUESTED = "NOT_REQUESTED", "No solicitada"
        INVOICE_REQUESTED = "INVOICE_REQUESTED", "Solicitada"
        INVOICE_PROCESSING = "INVOICE_PROCESSING", "Procesando"
        INVOICED = "INVOICED", "Facturada"
        INVOICE_FAILED = "INVOICE_FAILED", "Fallida"

    class PaymentCondition(models.TextChoices):
        CASH = "CASH", "Contado"
        CREDIT = "CREDIT", "Credito"

    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        PARTIAL = "PARTIAL", "Pago parcial"
        PAID = "PAID", "Pagado"

    objects = CompanyScopedManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.PROTECT, related_name="pos_transactions"
    )
    store = models.ForeignKey(
        "companies.Store", on_delete=models.PROTECT, related_name="pos_transactions"
    )
    register = models.ForeignKey(
        PosRegister, on_delete=models.PROTECT, related_name="transactions"
    )
    cash_session = models.ForeignKey(
        CashSession, on_delete=models.PROTECT, related_name="transactions"
    )
    sales_document = models.OneToOneField(
        "sales.SalesDocument", on_delete=models.PROTECT, related_name="pos_transaction"
    )
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="pos_transactions",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROCESSING)
    billing_status = models.CharField(
        max_length=25, choices=BillingStatus.choices, default=BillingStatus.NOT_REQUESTED
    )
    payment_condition = models.CharField(
        max_length=10,
        choices=PaymentCondition.choices,
        default=PaymentCondition.CASH,
    )
    payment_status = models.CharField(
        max_length=10,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    idempotency_key = models.UUIDField()
    ticket_number = models.PositiveBigIntegerField()
    ticket_code = models.CharField(max_length=30)
    device_identifier = models.CharField(max_length=120, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    failure_code = models.CharField(max_length=60, blank=True)
    failure_message = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = "pos_transactions"
        ordering = ("-started_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("company", "register", "idempotency_key"),
                name="uniq_pos_idempotency_key",
            ),
            models.UniqueConstraint(
                fields=("register", "ticket_number"), name="uniq_pos_ticket_number"
            ),
        ]

    def clean(self):
        errors = {}
        if self.register_id:
            if self.company_id != self.register.company_id or self.store_id != self.register.store_id:
                errors["register"] = "La caja no pertenece al contexto de la transaccion."
        if self.cash_session_id:
            if self.cash_session.register_id != self.register_id:
                errors["cash_session"] = "La sesion no pertenece a la caja seleccionada."
        if self.sales_document_id and self.sales_document.store_id != self.store_id:
            errors["sales_document"] = "El documento no pertenece a la sucursal del POS."
        if self.status == self.Status.COMPLETED and not self.completed_at:
            errors["completed_at"] = "Una transaccion completada requiere fecha de finalizacion."
        due_date = self.sales_document.due_date if self.sales_document_id else None
        if self.payment_condition == self.PaymentCondition.CASH and due_date:
            errors["payment_condition"] = "Una venta al contado no debe tener vencimiento."
        if self.payment_condition == self.PaymentCondition.CREDIT and not due_date:
            errors["payment_condition"] = "Una venta a credito requiere fecha de vencimiento."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.ticket_code


class SalesPayment(TimeStampedModel):
    class Status(models.TextChoices):
        REGISTERED = "REGISTERED", "Registrado"
        CANCELLED = "CANCELLED", "Cancelado"
        REFUNDED = "REFUNDED", "Devuelto"

    class Purpose(models.TextChoices):
        SALE_CHECKOUT = "SALE_CHECKOUT", "Pago durante la venta"
        CREDIT_COLLECTION = "CREDIT_COLLECTION", "Cobranza de credito"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sales_document = models.ForeignKey(
        "sales.SalesDocument", on_delete=models.PROTECT, related_name="pos_payments"
    )
    cash_session = models.ForeignKey(
        CashSession, on_delete=models.PROTECT, related_name="sales_payments"
    )
    means_of_payment = models.ForeignKey(
        "sales.MeansOfPayment", on_delete=models.PROTECT, related_name="pos_payments"
    )
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.REGISTERED)
    purpose = models.CharField(
        max_length=20, choices=Purpose.choices, default=Purpose.SALE_CHECKOUT
    )
    idempotency_key = models.UUIDField(null=True, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="PEN")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=6, default=1)
    amount_in_sale_currency = models.DecimalField(max_digits=14, decimal_places=2)
    received_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    change_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    operation_reference = models.CharField(max_length=120, blank=True)
    paid_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="created_pos_payments",
    )

    class Meta:
        db_table = "pos_sales_payments"
        ordering = ("paid_at",)
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="pos_payment_amount_gt_zero"),
            models.CheckConstraint(
                condition=models.Q(exchange_rate__gt=0), name="pos_payment_exchange_rate_gt_zero"
            ),
            models.CheckConstraint(
                condition=models.Q(amount_in_sale_currency__gt=0),
                name="pos_payment_sale_amount_gt_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(received_amount__gte=0), name="pos_payment_received_gte_zero"
            ),
            models.CheckConstraint(
                condition=models.Q(change_amount__gte=0), name="pos_payment_change_gte_zero"
            ),
            models.UniqueConstraint(
                fields=("cash_session", "idempotency_key"),
                condition=models.Q(idempotency_key__isnull=False),
                name="uniq_pos_payment_session_idempotency",
            ),
        ]

    def clean(self):
        errors = {}
        if self.sales_document_id and self.cash_session_id:
            if self.sales_document.store_id != self.cash_session.store_id:
                errors["cash_session"] = "El pago y la venta deben pertenecer a la misma sucursal."
            if self.currency != self.cash_session.currency:
                errors["currency"] = "La moneda del pago debe coincidir con la sesion de caja."
            try:
                pos_transaction = self.sales_document.pos_transaction
            except PosTransaction.DoesNotExist:
                pos_transaction = None
            if (
                pos_transaction
                and self.purpose == self.Purpose.SALE_CHECKOUT
                and pos_transaction.cash_session_id != self.cash_session_id
            ):
                errors["cash_session"] = "El pago no pertenece a la sesion de la venta POS."
        if self.means_of_payment_id and self.cash_session_id:
            if self.means_of_payment.company_id != self.cash_session.company_id:
                errors["means_of_payment"] = "El medio de pago pertenece a otra empresa."
        if errors:
            raise ValidationError(errors)


class PosReturn(TimeStampedModel):
    """Devolución POS total o parcial, independiente de la anulación fiscal."""

    class Status(models.TextChoices):
        COMPLETED = "COMPLETED", "Completada"
        CANCELLED = "CANCELLED", "Cancelada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.PROTECT, related_name="pos_returns"
    )
    store = models.ForeignKey(
        "companies.Store", on_delete=models.PROTECT, related_name="pos_returns"
    )
    register = models.ForeignKey(
        PosRegister, on_delete=models.PROTECT, related_name="returns"
    )
    cash_session = models.ForeignKey(
        CashSession, on_delete=models.PROTECT, related_name="returns"
    )
    original_transaction = models.ForeignKey(
        PosTransaction, on_delete=models.PROTECT, related_name="returns"
    )
    credit_note = models.OneToOneField(
        "sales.SalesDocument", on_delete=models.PROTECT, null=True, blank=True,
        related_name="pos_return",
    )
    inventory_movement = models.OneToOneField(
        "inventory.Movement", on_delete=models.PROTECT, null=True, blank=True,
        related_name="pos_return",
    )
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.COMPLETED
    )
    idempotency_key = models.UUIDField()
    reason_code = models.CharField(max_length=5, blank=True)
    reason = models.CharField(max_length=500)
    currency = models.CharField(max_length=3, default="PEN")
    total = models.DecimalField(max_digits=14, decimal_places=2)
    completed_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="created_pos_returns",
    )

    class Meta:
        db_table = "pos_returns"
        ordering = ("-completed_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("company", "register", "idempotency_key"),
                name="uniq_pos_return_idempotency_key",
            ),
            models.CheckConstraint(
                condition=models.Q(total__gt=0), name="pos_return_total_gt_zero"
            ),
        ]

    def clean(self):
        errors = {}
        if self.register_id and (
            self.register.company_id != self.company_id
            or self.register.store_id != self.store_id
        ):
            errors["register"] = "La caja no pertenece al contexto de la devolución."
        if self.cash_session_id and self.cash_session.register_id != self.register_id:
            errors["cash_session"] = "La sesión no pertenece a la caja de devolución."
        if self.original_transaction_id and (
            self.original_transaction.company_id != self.company_id
            or self.original_transaction.store_id != self.store_id
        ):
            errors["original_transaction"] = "La venta pertenece a otro contexto."
        if self.credit_note_id and self.credit_note.store_id != self.store_id:
            errors["credit_note"] = "La nota de crédito pertenece a otra sucursal."
        if errors:
            raise ValidationError(errors)


class PosReturnLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pos_return = models.ForeignKey(
        PosReturn, on_delete=models.CASCADE, related_name="lines"
    )
    original_line = models.ForeignKey(
        "sales.SalesDocumentLine", on_delete=models.PROTECT, related_name="pos_return_lines"
    )
    product = models.ForeignKey(
        "inventory.Product", on_delete=models.PROTECT, related_name="pos_return_lines"
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    stock_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    total = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        db_table = "pos_return_lines"
        constraints = [
            models.UniqueConstraint(
                fields=("pos_return", "original_line"), name="uniq_pos_return_original_line"
            ),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="pos_return_line_qty_gt_zero"),
            models.CheckConstraint(
                condition=models.Q(stock_quantity__gte=0), name="pos_return_line_stock_gte_zero"
            ),
            models.CheckConstraint(condition=models.Q(total__gt=0), name="pos_return_line_total_gt_zero"),
        ]


class PosRefundPayment(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pos_return = models.ForeignKey(
        PosReturn, on_delete=models.PROTECT, related_name="refund_payments"
    )
    cash_session = models.ForeignKey(
        CashSession, on_delete=models.PROTECT, related_name="refund_payments"
    )
    means_of_payment = models.ForeignKey(
        "sales.MeansOfPayment", on_delete=models.PROTECT, related_name="pos_refund_payments"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    operation_reference = models.CharField(max_length=120, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="created_pos_refund_payments",
    )

    class Meta:
        db_table = "pos_refund_payments"
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="pos_refund_payment_gt_zero")
        ]

    def clean(self):
        errors = {}
        if self.pos_return_id and self.cash_session_id != self.pos_return.cash_session_id:
            errors["cash_session"] = "El reembolso debe pertenecer a la sesión de la devolución."
        if self.means_of_payment_id and self.cash_session_id:
            if self.means_of_payment.company_id != self.cash_session.company_id:
                errors["means_of_payment"] = "El medio de devolución pertenece a otra empresa."
        if errors:
            raise ValidationError(errors)


class CashTenderDeclaration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cash_session = models.ForeignKey(
        CashSession, on_delete=models.CASCADE, related_name="tender_declarations"
    )
    means_of_payment = models.ForeignKey(
        "sales.MeansOfPayment", on_delete=models.PROTECT, related_name="cash_declarations"
    )
    expected_amount = models.DecimalField(max_digits=14, decimal_places=2)
    counted_amount = models.DecimalField(max_digits=14, decimal_places=2)
    difference = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        db_table = "pos_cash_tender_declarations"
        constraints = [
            models.UniqueConstraint(
                fields=("cash_session", "means_of_payment"),
                name="uniq_cash_tender_declaration",
            ),
        ]

    def clean(self):
        errors = {}
        if self.means_of_payment_id and self.cash_session_id:
            if self.means_of_payment.company_id != self.cash_session.company_id:
                errors["means_of_payment"] = "El medio de pago pertenece a otra empresa."
        if self.difference != self.counted_amount - self.expected_amount:
            errors["difference"] = "La diferencia no coincide con lo contado menos lo esperado."
        if errors:
            raise ValidationError(errors)


class SalesDocumentSource(TimeStampedModel):
    class SourceKind(models.TextChoices):
        POS_TICKET = "POS_TICKET", "Ticket POS"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_document = models.ForeignKey(
        "sales.SalesDocument", on_delete=models.PROTECT, related_name="target_document_links"
    )
    target_document = models.ForeignKey(
        "sales.SalesDocument", on_delete=models.PROTECT, related_name="source_document_links"
    )
    source_kind = models.CharField(
        max_length=20, choices=SourceKind.choices, default=SourceKind.POS_TICKET
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="created_sales_document_links",
    )

    class Meta:
        db_table = "pos_sales_document_sources"
        constraints = [
            models.UniqueConstraint(fields=("source_document",), name="uniq_invoiced_pos_ticket"),
            models.CheckConstraint(
                condition=~models.Q(source_document=models.F("target_document")),
                name="pos_source_differs_from_target",
            ),
        ]

    def clean(self):
        errors = {}
        source = self.source_document
        target = self.target_document
        if source.pk == target.pk:
            errors["target_document"] = "El documento destino debe ser diferente al origen."
        if source.store_id != target.store_id:
            errors["target_document"] = "Los documentos deben pertenecer a la misma sucursal."
        if source.customer_id != target.customer_id or source.customer_id is None:
            errors["target_document"] = "Los documentos deben pertenecer al mismo cliente identificado."
        if source.currency != target.currency:
            errors["target_document"] = "Los documentos deben utilizar la misma moneda."
        if source.document_type.code != "NV":
            errors["source_document"] = "Solo una Nota de Venta puede consolidarse."
        if target.document_type.code != "01":
            errors["target_document"] = "El documento consolidado debe ser una factura."
        if target.status != "ISSUED":
            errors["target_document"] = "La factura consolidada debe estar emitida."
        if source.customer_id and source.customer.document_type != "6":
            errors["source_document"] = "La factura requiere un cliente identificado con RUC."
        if target.register_inventory_movement:
            errors["target_document"] = "La factura consolidada no debe volver a mover inventario."
        if errors:
            raise ValidationError(errors)
