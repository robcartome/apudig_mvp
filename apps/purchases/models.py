import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.managers import CompanyScopedManager
from apps.core.models import TimeStampedModel


class PurchaseDocumentStatus(models.TextChoices):
    DRAFT = "DRAFT", "Borrador"
    REGISTERED = "REGISTERED", "Registrado"
    CANCELLED = "CANCELLED", "Cancelado"


class PurchasePaymentStatus(models.TextChoices):
    UNPAID = "UNPAID", "No pagado"
    PARTIALLY_PAID = "PARTIALLY_PAID", "Parcialmente pagado"
    PAID = "PAID", "Pagado"


class PurchaseTaxType(models.TextChoices):
    TAXED = "10", "Gravado IGV"
    EXEMPT = "20", "Exonerado"
    UNAFFECTED = "30", "Inafecto"
    IMPORT = "40", "Importacion"


class PurchaseOrderStatus(models.TextChoices):
    DRAFT = "DRAFT", "Borrador"
    APPROVED = "APPROVED", "Aprobada"
    CLOSED = "CLOSED", "Cerrada"
    CANCELLED = "CANCELLED", "Cancelada"


class PurchaseReceiptStatus(models.TextChoices):
    REGISTERED = "REGISTERED", "Registrada"
    CANCELLED = "CANCELLED", "Cancelada"


class SupplierPaymentStatus(models.TextChoices):
    REGISTERED = "REGISTERED", "Registrado"
    CANCELLED = "CANCELLED", "Anulado"


class LandedCostStatus(models.TextChoices):
    ALLOCATED = "ALLOCATED", "Distribuido"
    CANCELLED = "CANCELLED", "Anulado"


class LandedCostAllocationMethod(models.TextChoices):
    VALUE = "VALUE", "Por valor"
    QUANTITY = "QUANTITY", "Por cantidad base"
    MANUAL = "MANUAL", "Manual"


class PurchaseCategory(TimeStampedModel):
    objects = CompanyScopedManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE, related_name="purchase_categories"
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "purchase_categories"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=("company", "code"), name="uniq_company_purchase_category_code"
            )
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class PurchaseOrder(TimeStampedModel):
    """Commercial commitment to a supplier; it does not receive or invoice goods."""

    objects = CompanyScopedManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE, related_name="purchase_orders"
    )
    store = models.ForeignKey(
        "companies.Store", on_delete=models.PROTECT, related_name="purchase_orders"
    )
    supplier = models.ForeignKey(
        "partners.Supplier", on_delete=models.PROTECT, related_name="purchase_orders"
    )
    order_number = models.CharField(max_length=30)
    order_date = models.DateField()
    expected_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=PurchaseOrderStatus.choices,
        default=PurchaseOrderStatus.DRAFT,
    )
    currency = models.CharField(max_length=3, default="PEN")
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=6, default=1)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    igv_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="purchase_orders_created",
    )

    class Meta:
        db_table = "purchase_orders"
        ordering = ["-order_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("company", "order_number"), name="uniq_company_purchase_order_number"
            ),
            models.CheckConstraint(
                condition=models.Q(exchange_rate__gt=0), name="purchase_order_exchange_rate_gt_zero"
            ),
        ]

    def clean(self):
        errors = {}
        if self.store_id and str(self.store.company_id) != str(self.company_id):
            errors["store"] = "La sucursal debe pertenecer a la empresa de la orden."
        if self.supplier_id and str(self.supplier.company_id) != str(self.company_id):
            errors["supplier"] = "El proveedor debe pertenecer a la empresa de la orden."
        if self.expected_date and self.order_date and self.expected_date < self.order_date:
            errors["expected_date"] = "La fecha esperada no puede ser anterior a la orden."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.order_number} - {self.supplier}"


class PurchaseOrderLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="lines"
    )
    position = models.PositiveIntegerField()
    product = models.ForeignKey(
        "inventory.Product", on_delete=models.PROTECT, null=True, blank=True,
        related_name="purchase_order_lines",
    )
    purchase_category = models.ForeignKey(
        PurchaseCategory, on_delete=models.PROTECT, null=True, blank=True,
        related_name="order_lines",
    )
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit = models.ForeignKey(
        "inventory.Unit", on_delete=models.PROTECT, null=True, blank=True,
        related_name="purchase_order_lines",
    )
    unit_code = models.CharField(max_length=10)
    conversion_factor = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    unit_price = models.DecimalField(max_digits=14, decimal_places=6)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_type = models.CharField(max_length=5, choices=PurchaseTaxType.choices, default=PurchaseTaxType.TAXED)
    igv_rate = models.DecimalField(max_digits=5, decimal_places=2, default=18)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    igv_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    memo = models.CharField(max_length=1000, blank=True)

    class Meta:
        db_table = "purchase_order_lines"
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=("purchase_order", "position"), name="uniq_purchase_order_line_position"),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="purchase_order_line_quantity_gt_zero"),
            models.CheckConstraint(condition=models.Q(unit_price__gte=0), name="purchase_order_line_price_gte_zero"),
            models.CheckConstraint(
                condition=(
                    models.Q(product__isnull=False, purchase_category__isnull=True)
                    | models.Q(product__isnull=True, purchase_category__isnull=False)
                ), name="purchase_order_line_product_xor_category",
            ),
        ]

    def clean(self):
        if bool(self.product_id) == bool(self.purchase_category_id):
            raise ValidationError("La linea debe tener un producto o una categoria de compra.")
        concept = self.product if self.product_id else self.purchase_category
        if concept and self.purchase_order_id and str(concept.company_id) != str(self.purchase_order.company_id):
            raise ValidationError("El producto o categoria debe pertenecer a la empresa de la orden.")


class PurchaseReceipt(TimeStampedModel):
    """Physical receipt against an order; each receipt creates one inventory entry."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name="receipts"
    )
    warehouse = models.ForeignKey(
        "inventory.Warehouse", on_delete=models.PROTECT, related_name="purchase_receipts"
    )
    receipt_number = models.CharField(max_length=30)
    receipt_date = models.DateTimeField()
    status = models.CharField(
        max_length=20, choices=PurchaseReceiptStatus.choices,
        default=PurchaseReceiptStatus.REGISTERED,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="purchase_receipts_created",
    )

    class Meta:
        db_table = "purchase_receipts"
        ordering = ["-receipt_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("purchase_order", "receipt_number"),
                name="uniq_purchase_order_receipt_number",
            )
        ]


class PurchaseReceiptLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_receipt = models.ForeignKey(
        PurchaseReceipt, on_delete=models.CASCADE, related_name="lines"
    )
    purchase_order_line = models.ForeignKey(
        PurchaseOrderLine, on_delete=models.PROTECT, related_name="receipt_lines"
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=4)

    class Meta:
        db_table = "purchase_receipt_lines"
        constraints = [
            models.UniqueConstraint(
                fields=("purchase_receipt", "purchase_order_line"),
                name="uniq_receipt_order_line",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="purchase_receipt_line_quantity_gt_zero"
            ),
        ]


class PurchaseDocument(TimeStampedModel):
    """Commercial document received from a supplier.

    A purchase document is deliberately independent from purchase orders,
    physical inventory receipts and vendor payments.
    """

    objects = CompanyScopedManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE, related_name="purchase_documents"
    )
    store = models.ForeignKey(
        "companies.Store", on_delete=models.PROTECT, related_name="purchase_documents"
    )
    supplier = models.ForeignKey(
        "partners.Supplier", on_delete=models.PROTECT, related_name="purchase_documents"
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="purchase_documents",
    )
    document_type = models.ForeignKey(
        "partners.DocumentType", on_delete=models.PROTECT, related_name="purchase_documents"
    )
    document_status = models.CharField(
        max_length=20,
        choices=PurchaseDocumentStatus.choices,
        default=PurchaseDocumentStatus.DRAFT,
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PurchasePaymentStatus.choices,
        default=PurchasePaymentStatus.UNPAID,
    )
    payment_method = models.ForeignKey(
        "sales.PaymentMethod", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="purchase_documents", verbose_name="Condicion de pago",
    )
    supplier_document_number = models.CharField(max_length=20)
    supplier_name = models.CharField(max_length=255)
    supplier_address = models.CharField(max_length=500, blank=True)
    series = models.CharField(max_length=20, blank=True)
    number = models.CharField(max_length=30, blank=True)
    issue_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="PEN")
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=6, default=1)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    taxable_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    exempt_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    unaffected_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    igv_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    register_inventory_movement = models.BooleanField(default=True)
    warehouse = models.ForeignKey(
        "inventory.Warehouse",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_documents",
    )
    notes = models.TextField(blank=True)
    internal_reference = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_documents",
    )

    class Meta:
        db_table = "purchase_documents"
        ordering = ["-issue_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("company", "supplier", "document_type", "series", "number"),
                condition=~models.Q(number=""),
                name="uniq_supplier_purchase_document_number",
            ),
            models.CheckConstraint(
                condition=models.Q(exchange_rate__gt=0),
                name="purchase_document_exchange_rate_gt_zero",
            ),
        ]

    def clean(self):
        errors = {}
        if self.store_id and str(self.company_id) != str(self.store.company_id):
            errors["store"] = "La sucursal debe pertenecer a la empresa del documento."
        if self.supplier_id and str(self.company_id) != str(self.supplier.company_id):
            errors["supplier"] = "El proveedor debe pertenecer a la empresa del documento."
        if self.warehouse_id and str(self.store_id) != str(self.warehouse.store_id):
            errors["warehouse"] = "El almacen debe pertenecer a la sucursal del documento."
        if self.purchase_order_id:
            if str(self.purchase_order.company_id) != str(self.company_id) or str(self.purchase_order.store_id) != str(self.store_id):
                errors["purchase_order"] = "La orden debe pertenecer a la empresa y sucursal del documento."
            elif str(self.purchase_order.supplier_id) != str(self.supplier_id):
                errors["purchase_order"] = "La orden debe pertenecer al mismo proveedor del documento."
        if self.due_date and self.issue_date and self.due_date < self.issue_date:
            errors["due_date"] = "La fecha de vencimiento no puede ser anterior a la emision."
        if self.payment_method_id:
            if str(self.payment_method.company_id) != str(self.company_id):
                errors["payment_method"] = "La condicion de pago no pertenece a la empresa."
            elif self.payment_method.is_cash and self.issue_date:
                self.due_date = self.issue_date
            elif not self.payment_method.is_cash and not self.due_date:
                errors["due_date"] = "Indica la fecha de vencimiento para una compra a credito."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        reference = "-".join(part for part in (self.series, self.number) if part)
        return f"{self.document_type.code} {reference} - {self.supplier_name}".strip()

    @property
    def is_expense(self):
        """Identifica documentos creados desde el flujo separado de gastos."""
        lines = self.lines.all()
        return bool(lines) and all(line.purchase_category_id for line in lines)


class PurchaseDocumentLine(models.Model):
    """Immutable commercial values invoiced by the supplier."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_document = models.ForeignKey(
        PurchaseDocument, on_delete=models.CASCADE, related_name="lines"
    )
    position = models.PositiveIntegerField()
    product = models.ForeignKey(
        "inventory.Product", on_delete=models.PROTECT, null=True, blank=True,
        related_name="purchase_document_lines"
    )
    purchase_category = models.ForeignKey(
        PurchaseCategory, on_delete=models.PROTECT, null=True, blank=True,
        related_name="document_lines"
    )
    purchase_order_line = models.ForeignKey(
        PurchaseOrderLine, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="invoice_lines",
    )
    description = models.CharField(max_length=500)
    product_code = models.CharField(max_length=100, blank=True)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit = models.ForeignKey(
        "inventory.Unit", on_delete=models.PROTECT, null=True, blank=True,
        related_name="purchase_document_lines"
    )
    unit_code = models.CharField(max_length=10)
    conversion_factor = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    stock_quantity = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    unit_price = models.DecimalField(max_digits=14, decimal_places=6)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_type = models.CharField(
        max_length=5, choices=PurchaseTaxType.choices, default=PurchaseTaxType.TAXED
    )
    igv_rate = models.DecimalField(max_digits=5, decimal_places=2, default=18)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    igv_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    update_purchase_price = models.BooleanField(default=True)
    memo = models.CharField(max_length=1000, blank=True)

    class Meta:
        db_table = "purchase_document_lines"
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=("purchase_document", "position"),
                name="uniq_purchase_document_line_position",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="purchase_document_line_quantity_gt_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(conversion_factor__gt=0),
                name="purchase_document_line_factor_gt_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0),
                name="purchase_document_line_price_gte_zero",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(product__isnull=False, purchase_category__isnull=True)
                    | models.Q(product__isnull=True, purchase_category__isnull=False)
                ),
                name="purchase_line_product_xor_category",
            ),
        ]

    def clean(self):
        if bool(self.product_id) == bool(self.purchase_category_id):
            raise ValidationError("La linea debe tener un producto o una categoria de compra.")
        if (
            self.product_id
            and self.purchase_document_id
            and str(self.product.company_id) != str(self.purchase_document.company_id)
        ):
            raise ValidationError(
                {"product": "El producto debe pertenecer a la empresa del documento."}
            )
        if (
            self.purchase_category_id
            and self.purchase_document_id
            and str(self.purchase_category.company_id) != str(self.purchase_document.company_id)
        ):
            raise ValidationError(
                {"purchase_category": "La categoria debe pertenecer a la empresa del documento."}
            )

    def __str__(self):
        concept = self.product or self.purchase_category
        return f"{self.position}. {concept} x {self.quantity}"


class PurchasePayableInstallment(TimeStampedModel):
    """Scheduled payable created from a registered supplier document."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_document = models.ForeignKey(
        PurchaseDocument, on_delete=models.PROTECT, related_name="installments"
    )
    sequence = models.PositiveIntegerField(default=1)
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        db_table = "purchase_payable_installments"
        ordering = ("due_date", "sequence")
        constraints = [
            models.UniqueConstraint(
                fields=("purchase_document", "sequence"), name="uniq_document_installment_sequence"
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="purchase_installment_amount_gt_zero"
            ),
        ]

    def __str__(self):
        return f"{self.purchase_document} - Cuota {self.sequence}"


class SupplierPayment(TimeStampedModel):
    objects = CompanyScopedManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE, related_name="supplier_payments"
    )
    store = models.ForeignKey(
        "companies.Store", on_delete=models.PROTECT, related_name="supplier_payments"
    )
    supplier = models.ForeignKey(
        "partners.Supplier", on_delete=models.PROTECT, related_name="payments"
    )
    payment_number = models.CharField(max_length=30)
    payment_date = models.DateTimeField()
    currency = models.CharField(max_length=3, default="PEN")
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=6, default=1)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    means_of_payment = models.ForeignKey(
        "sales.MeansOfPayment", on_delete=models.PROTECT, related_name="supplier_payments"
    )
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=SupplierPaymentStatus.choices,
        default=SupplierPaymentStatus.REGISTERED,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="supplier_payments_created",
    )

    class Meta:
        db_table = "supplier_payments"
        ordering = ("-payment_date", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("company", "payment_number"), name="uniq_company_supplier_payment_number"
            ),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="supplier_payment_amount_gt_zero"),
            models.CheckConstraint(condition=models.Q(exchange_rate__gt=0), name="supplier_payment_exchange_rate_gt_zero"),
        ]

    def __str__(self):
        return f"{self.payment_number} - {self.supplier}"


class SupplierPaymentAllocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(
        SupplierPayment, on_delete=models.CASCADE, related_name="allocations"
    )
    installment = models.ForeignKey(
        PurchasePayableInstallment, on_delete=models.PROTECT, related_name="payment_allocations"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        db_table = "supplier_payment_allocations"
        constraints = [
            models.UniqueConstraint(
                fields=("payment", "installment"), name="uniq_payment_installment_allocation"
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="supplier_payment_allocation_amount_gt_zero"
            ),
        ]


class PurchaseLandedCost(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_document = models.ForeignKey(
        PurchaseDocument, on_delete=models.PROTECT, related_name="landed_costs"
    )
    description = models.CharField(max_length=200)
    reference = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    allocation_method = models.CharField(
        max_length=20, choices=LandedCostAllocationMethod.choices,
        default=LandedCostAllocationMethod.VALUE,
    )
    status = models.CharField(
        max_length=20, choices=LandedCostStatus.choices,
        default=LandedCostStatus.ALLOCATED,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="purchase_landed_costs_created",
    )

    class Meta:
        db_table = "purchase_landed_costs"
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="purchase_landed_cost_amount_gt_zero"
            )
        ]


class PurchaseLandedCostAllocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    landed_cost = models.ForeignKey(
        PurchaseLandedCost, on_delete=models.CASCADE, related_name="allocations"
    )
    purchase_document_line = models.ForeignKey(
        PurchaseDocumentLine, on_delete=models.PROTECT, related_name="landed_cost_allocations"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        db_table = "purchase_landed_cost_allocations"
        constraints = [
            models.UniqueConstraint(
                fields=("landed_cost", "purchase_document_line"),
                name="uniq_landed_cost_document_line",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gte=0), name="purchase_landed_allocation_amount_gte_zero"
            ),
        ]
