from django.db import migrations


DOCUMENT_TYPES = {
    "FACTURA": "01",
    "BOLETA": "03",
    "CREDIT_NOTE": "07",
    "DEBIT_NOTE": "08",
    "REMISSION_GUIDE": "09",
}


def consolidate_invoices(apps, schema_editor):
    BillingInvoice = apps.get_model("billing", "BillingInvoice")
    BillingInvoiceLine = apps.get_model("billing", "BillingInvoiceLine")
    SalesDocument = apps.get_model("sales", "SalesDocument")
    SalesDocumentLine = apps.get_model("sales", "SalesDocumentLine")

    if BillingInvoiceLine.objects.filter(product_id__isnull=True).exists():
        raise RuntimeError(
            "Cannot consolidate billing lines without a product. Assign products before migrating."
        )

    for invoice in BillingInvoice.objects.all().iterator():
        customer = invoice.customer
        document, _ = SalesDocument.objects.get_or_create(
            id=invoice.id,
            defaults={
                "document_type": DOCUMENT_TYPES.get(invoice.document_type, "01"),
                "status": invoice.status,
                "customer_id": invoice.customer_id,
                "customer_document_type": getattr(customer, "document_type", "") or "0",
                "customer_document_number": invoice.customer_document_number,
                "customer_legal_name": invoice.customer_name,
                "customer_address": getattr(customer, "address", "") or "",
                "issue_date": invoice.issue_date.date(),
                "currency": invoice.currency,
                "series_code": invoice.series[:4],
                "number": invoice.number[:8],
                "subtotal": invoice.subtotal,
                "taxable_amount": invoice.subtotal,
                "igv_total": invoice.igv_total,
                "total": invoice.total,
                "notes": invoice.notes,
                "sunat_ticket": invoice.sunat_ticket,
                "sunat_response_code": invoice.sunat_response_code,
                "sunat_response_message": invoice.sunat_response_message,
                "created_by_id": invoice.created_by_id,
            },
        )
        lines = BillingInvoiceLine.objects.filter(invoice_id=invoice.id)
        for line in lines:
            SalesDocumentLine.objects.get_or_create(
                id=line.id,
                defaults={
                    "sales_document_id": document.id,
                    "product_id": line.product_id,
                    "description": line.description,
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                    "unit_code": "NIU",
                    "tax_type": "10",
                    "igv_rate": line.igv_rate,
                    "subtotal": line.line_subtotal,
                    "igv_amount": line.line_igv,
                    "total": line.line_total,
                },
            )


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0004_rename_core_customer_field"),
        ("sales", "0005_rename_voucher_to_sales_document"),
    ]

    operations = [
        migrations.RunPython(consolidate_invoices, migrations.RunPython.noop),
        migrations.DeleteModel(name="BillingInvoiceLine"),
        migrations.DeleteModel(name="BillingInvoice"),
    ]
