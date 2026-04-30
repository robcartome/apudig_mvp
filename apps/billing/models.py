import uuid

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


INVOICE_DOC_TYPE_CHOICES = [
    ("FACTURA", "Factura"),
    ("BOLETA", "Boleta"),
    ("CREDIT_NOTE", "Nota de Crédito"),
    ("DEBIT_NOTE", "Nota de Débito"),
    ("REMISSION_GUIDE", "Guía de Remisión"),
]

INVOICE_STATUS_CHOICES = [
    ("DRAFT", "Borrador"),
    ("ISSUED", "Emitido"),
    ("SUNAT_PENDING", "Pendiente SUNAT"),
    ("SUNAT_ACCEPTED", "Aceptado SUNAT"),
    ("SUNAT_REJECTED", "Rechazado SUNAT"),
    ("VOIDED", "Anulado"),
]


class BillingInvoice(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_type = models.CharField(max_length=20, choices=INVOICE_DOC_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=INVOICE_STATUS_CHOICES, default="DRAFT")
    series = models.CharField(max_length=10, blank=True)
    number = models.CharField(max_length=20, blank=True)
    issue_date = models.DateTimeField()
    core_customer = models.ForeignKey(
        "partners.CoreCustomer", on_delete=models.SET_NULL, null=True, blank=True, related_name="billing_invoices"
    )
    customer_name = models.CharField(max_length=255)
    customer_document_number = models.CharField(max_length=20)
    currency = models.CharField(max_length=3, default="PEN")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    igv_total = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.CharField(max_length=500, blank=True)
    sunat_ticket = models.CharField(max_length=120, blank=True)
    sunat_response_code = models.CharField(max_length=50, blank=True)
    sunat_response_message = models.CharField(max_length=500, blank=True)
    business_document_type = models.ForeignKey(
        "sales.BusinessDocumentType", on_delete=models.SET_NULL, null=True, blank=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="billing_invoices"
    )

    class Meta:
        db_table = "billing_invoices"
        ordering = ["-issue_date"]

    def __str__(self) -> str:
        return f"{self.document_type} {self.series}-{self.number}"


class BillingInvoiceLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(BillingInvoice, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(
        "inventory.Product", on_delete=models.SET_NULL, null=True, blank=True, related_name="billing_lines"
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=3)
    igv_rate = models.DecimalField(max_digits=5, decimal_places=2)
    line_subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    line_igv = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "billing_invoice_lines"
