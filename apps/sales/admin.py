from django.contrib import admin

from .models import (
    DocumentSeries,
    SaleOrder,
    SaleOrderLine,
    SalesQuotation,
    SalesQuotationLine,
    SalesDocument,
    SalesDocumentLine,
)


@admin.register(DocumentSeries)
class DocumentSeriesAdmin(admin.ModelAdmin):
    list_display = ("series", "document_type", "company", "store", "current_number", "active")
    list_filter = ("document_type", "company", "active")
    search_fields = ("series",)


class SalesQuotationLineInline(admin.TabularInline):
    model = SalesQuotationLine
    extra = 0
    fields = ("product", "description", "quantity", "unit_price", "subtotal", "igv_amount", "total")
    readonly_fields = ("subtotal", "igv_amount", "total")


@admin.register(SalesQuotation)
class SalesQuotationAdmin(admin.ModelAdmin):
    list_display = ("series_code", "number", "customer", "issue_date", "status", "total", "currency")
    list_filter = ("status", "currency", "store")
    search_fields = ("customer__legal_name", "customer__document_number", "series_code")
    inlines = [SalesQuotationLineInline]


class SaleOrderLineInline(admin.TabularInline):
    model = SaleOrderLine
    extra = 0
    fields = ("product", "description", "quantity", "unit_price", "subtotal", "igv_amount", "total")
    readonly_fields = ("subtotal", "igv_amount", "total")


@admin.register(SaleOrder)
class SaleOrderAdmin(admin.ModelAdmin):
    list_display = ("series_code", "number", "customer", "issue_date", "status", "total", "currency")
    list_filter = ("status", "currency", "store")
    search_fields = ("customer__legal_name", "series_code", "number")
    inlines = [SaleOrderLineInline]


class SalesDocumentLineInline(admin.TabularInline):
    model = SalesDocumentLine
    extra = 0
    fields = ("product", "description", "quantity", "unit_price", "subtotal", "igv_amount", "total")
    readonly_fields = ("subtotal", "igv_amount", "total")


@admin.register(SalesDocument)
class SalesDocumentAdmin(admin.ModelAdmin):
    list_display = ("document_type", "series_code", "number", "customer", "issue_date", "status", "total")
    list_filter = ("document_type", "status", "store")
    search_fields = ("customer__legal_name", "series_code", "number")
    inlines = [SalesDocumentLineInline]
