from django.contrib import admin

from .models import BillingInvoice, BillingInvoiceLine


class BillingInvoiceLineInline(admin.TabularInline):
    model = BillingInvoiceLine
    extra = 0
    fields = ("product", "description", "quantity", "unit_price", "igv_rate", "line_total")


@admin.register(BillingInvoice)
class BillingInvoiceAdmin(admin.ModelAdmin):
    list_display = ("series", "number", "document_type", "status", "customer_name", "total", "issue_date")
    list_filter = ("document_type", "status")
    search_fields = ("customer_name", "customer_document_number", "series", "number")
    inlines = [BillingInvoiceLineInline]
