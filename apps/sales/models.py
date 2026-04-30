import uuid

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


# ── Enums / choices ───────────────────────────────────────────────────────────

VOUCHER_TYPE_CHOICES = [
    ("01", "Factura"),
    ("03", "Boleta de Venta"),
    ("07", "Nota de Crédito"),
    ("08", "Nota de Débito"),
    ("09", "Guía de Remisión"),
    ("OV", "Orden de Venta"),
    ("COT", "Cotización"),
]

VOUCHER_STATUS_CHOICES = [
    ("DRAFT", "Borrador"),
    ("ISSUED", "Emitido"),
    ("SUNAT_PENDING", "Pendiente SUNAT"),
    ("SUNAT_ACCEPTED", "Aceptado SUNAT"),
    ("SUNAT_OBSERVED", "Observado SUNAT"),
    ("SUNAT_REJECTED", "Rechazado SUNAT"),
    ("VOIDED", "Anulado"),
    ("CANCELLED", "Cancelado"),
]

QUOTATION_STATUS_CHOICES = [
    ("DRAFT", "Borrador"),
    ("SENT", "Enviado"),
    ("APPROVED", "Aprobado"),
    ("REJECTED", "Rechazado"),
    ("CANCELLED", "Cancelado"),
]

SALE_ORDER_STATUS_CHOICES = [
    ("DRAFT", "Borrador"),
    ("CONFIRMED", "Confirmado"),
    ("INVOICED", "Facturado"),
    ("CANCELLED", "Cancelado"),
]

TAX_TYPE_CHOICES = [
    ("10", "Gravado IGV"),
    ("20", "Exonerado"),
    ("30", "Inafecto"),
    ("40", "Exportación"),
    ("11", "IGV retiro"),
]

DOC_CATEGORY_CHOICES = [
    ("SALES", "Ventas"),
    ("BILLING", "Facturación"),
    ("LOGISTICS", "Logística"),
    ("INTERNAL", "Interno"),
]


# ── Catálogos de documento ────────────────────────────────────────────────────

class BusinessDocumentType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=20, choices=DOC_CATEGORY_CHOICES)
    is_sunat = models.BooleanField(default=False)
    sunat_code = models.CharField(max_length=4, blank=True)
    affects_stock = models.BooleanField(default=False)
    affects_accounting = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "business_document_types"
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class DocumentSeries(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="document_series")
    store = models.ForeignKey(
        "companies.Store", on_delete=models.SET_NULL, null=True, blank=True, related_name="document_series"
    )
    voucher_type = models.CharField(max_length=10, choices=VOUCHER_TYPE_CHOICES)
    series = models.CharField(max_length=4)
    current_number = models.IntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "document_series"
        unique_together = ("company", "store", "voucher_type", "series")

    def __str__(self) -> str:
        return f"{self.series} ({self.voucher_type})"

    def next_number(self) -> int:
        self.current_number += 1
        self.save(update_fields=["current_number"])
        return self.current_number


# ── Líneas base (mixin abstracto) ─────────────────────────────────────────────

class SaleLineBase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT)
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit_price = models.DecimalField(max_digits=14, decimal_places=6)
    unit_code = models.CharField(max_length=10, default="NIU")
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_type = models.CharField(max_length=5, choices=TAX_TYPE_CHOICES, default="10")
    igv_rate = models.DecimalField(max_digits=5, decimal_places=2, default=18)
    sunat_product_code = models.CharField(max_length=30, blank=True)
    product_code = models.CharField(max_length=50, blank=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    igv_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        abstract = True


# ── Cotizaciones ──────────────────────────────────────────────────────────────

class SalesQuotation(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        "companies.Store", on_delete=models.SET_NULL, null=True, blank=True, related_name="quotations"
    )
    customer = models.ForeignKey(
        "partners.CoreCustomer", on_delete=models.PROTECT, related_name="quotations"
    )
    customer_document_type = models.CharField(max_length=2)
    customer_document_number = models.CharField(max_length=15)
    customer_legal_name = models.CharField(max_length=300)
    customer_address = models.CharField(max_length=500, blank=True)
    customer_ubigeo = models.CharField(max_length=6, blank=True)
    issue_date = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="PEN")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=6, default=1)
    status = models.CharField(max_length=20, choices=QUOTATION_STATUS_CHOICES, default="DRAFT")
    source_quotation = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="revisions"
    )
    version_number = models.IntegerField(default=1)
    series = models.ForeignKey(
        DocumentSeries, on_delete=models.SET_NULL, null=True, blank=True, related_name="quotations"
    )
    series_code = models.CharField(max_length=10, blank=True)
    number = models.IntegerField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    igv_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    internal_reference = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="quotations"
    )

    class Meta:
        db_table = "sales_quotations"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"COT {self.series_code}-{self.number or ''} ({self.status})"


class SalesQuotationLine(SaleLineBase):
    quotation = models.ForeignKey(SalesQuotation, on_delete=models.CASCADE, related_name="lines")
    memo = models.CharField(max_length=1000, blank=True)

    class Meta:
        db_table = "sales_quotation_lines"


# ── Órdenes de venta ──────────────────────────────────────────────────────────

class SaleOrder(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        "companies.Store", on_delete=models.SET_NULL, null=True, blank=True, related_name="sale_orders"
    )
    customer = models.ForeignKey("partners.CoreCustomer", on_delete=models.PROTECT, related_name="sale_orders")
    customer_document_type = models.CharField(max_length=2)
    customer_document_number = models.CharField(max_length=15)
    customer_legal_name = models.CharField(max_length=300)
    customer_address = models.CharField(max_length=500, blank=True)
    customer_ubigeo = models.CharField(max_length=6, blank=True)
    document_type = models.ForeignKey(
        BusinessDocumentType, on_delete=models.PROTECT, related_name="sale_orders"
    )
    status = models.CharField(max_length=20, choices=SALE_ORDER_STATUS_CHOICES, default="DRAFT")
    currency = models.CharField(max_length=3, default="PEN")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=6, default=1)
    payment_term_days = models.IntegerField(default=0)
    issue_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    series = models.ForeignKey(
        DocumentSeries, on_delete=models.SET_NULL, null=True, blank=True, related_name="sale_orders"
    )
    series_code = models.CharField(max_length=4, blank=True)
    number = models.CharField(max_length=8, blank=True)
    quotation = models.ForeignKey(
        SalesQuotation, on_delete=models.SET_NULL, null=True, blank=True, related_name="sale_orders"
    )
    price_list = models.ForeignKey(
        "inventory.PriceList", on_delete=models.SET_NULL, null=True, blank=True, related_name="sale_orders"
    )
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    igv_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    internal_reference = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="sale_orders"
    )

    class Meta:
        db_table = "sale_orders"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"OV {self.series_code}-{self.number} ({self.status})"


class SaleOrderLine(SaleLineBase):
    sale_order = models.ForeignKey(SaleOrder, on_delete=models.CASCADE, related_name="lines")

    class Meta:
        db_table = "sale_order_lines"


# ── Comprobantes ──────────────────────────────────────────────────────────────

class Voucher(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        "companies.Store", on_delete=models.SET_NULL, null=True, blank=True, related_name="vouchers"
    )
    voucher_type = models.CharField(max_length=10, choices=VOUCHER_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=VOUCHER_STATUS_CHOICES, default="DRAFT")
    customer = models.ForeignKey(
        "partners.CoreCustomer", on_delete=models.SET_NULL, null=True, blank=True, related_name="vouchers"
    )
    customer_document_type = models.CharField(max_length=2)
    customer_document_number = models.CharField(max_length=15)
    customer_legal_name = models.CharField(max_length=300)
    customer_address = models.CharField(max_length=500, blank=True)
    customer_ubigeo = models.CharField(max_length=6, blank=True)
    issue_date = models.DateField()
    currency = models.CharField(max_length=3, default="PEN")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=6, default=1)
    series = models.ForeignKey(
        DocumentSeries, on_delete=models.SET_NULL, null=True, blank=True, related_name="vouchers"
    )
    series_code = models.CharField(max_length=4, blank=True)
    number = models.CharField(max_length=8, blank=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    taxable_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    exempt_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    unaffected_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    igv_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    reference_voucher = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="credit_notes"
    )
    reference_series = models.CharField(max_length=4, blank=True)
    reference_number = models.CharField(max_length=8, blank=True)
    note_reason_code = models.CharField(max_length=5, blank=True)
    note_reason_description = models.CharField(max_length=200, blank=True)
    sale_order = models.ForeignKey(
        SaleOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name="vouchers"
    )
    sunat_ticket = models.CharField(max_length=100, blank=True)
    sunat_cdr_status = models.CharField(max_length=20, blank=True)
    sunat_response_code = models.CharField(max_length=10, blank=True)
    sunat_response_message = models.TextField(blank=True)
    sunat_xml_path = models.CharField(max_length=500, blank=True)
    sunat_cdr_path = models.CharField(max_length=500, blank=True)
    sunat_pdf_path = models.CharField(max_length=500, blank=True)
    sunat_hash = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="vouchers"
    )

    class Meta:
        db_table = "vouchers"
        ordering = ["-issue_date", "-created_at"]

    def __str__(self) -> str:
        return f"{self.voucher_type} {self.series_code}-{self.number}"


class VoucherLine(SaleLineBase):
    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name="lines")
    sale_order_line = models.ForeignKey(
        SaleOrderLine, on_delete=models.SET_NULL, null=True, blank=True, related_name="voucher_lines"
    )

    class Meta:
        db_table = "voucher_lines"
