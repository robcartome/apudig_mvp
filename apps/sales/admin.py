from django.contrib import admin

from .models import (
    BusinessDocumentType,
    DocumentSeries,
    SaleOrder,
    SaleOrderLine,
    SalesQuotation,
    SalesQuotationLine,
    Voucher,
    VoucherLine,
)


@admin.register(BusinessDocumentType)
class BusinessDocumentTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "is_sunat", "affects_stock", "active")
    list_filter = ("category", "is_sunat", "affects_stock", "active")
    search_fields = ("code", "name")


@admin.register(DocumentSeries)
class DocumentSeriesAdmin(admin.ModelAdmin):
    list_display = ("series", "voucher_type", "company", "store", "current_number", "active")
    list_filter = ("voucher_type", "company", "active")
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


class VoucherLineInline(admin.TabularInline):
    model = VoucherLine
    extra = 0
    fields = ("product", "description", "quantity", "unit_price", "subtotal", "igv_amount", "total")
    readonly_fields = ("subtotal", "igv_amount", "total")


@admin.register(Voucher)
class VoucherAdmin(admin.ModelAdmin):
    list_display = ("voucher_type", "series_code", "number", "customer", "issue_date", "status", "total")
    list_filter = ("voucher_type", "status", "store")
    search_fields = ("customer__legal_name", "series_code", "number")
    inlines = [VoucherLineInline]
