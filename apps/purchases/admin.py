from django.contrib import admin

from .models import (
    PurchaseCategory, PurchaseDocument, PurchaseDocumentLine,
    PurchaseOrder, PurchaseOrderLine,
    PurchaseReceipt, PurchaseReceiptLine,
    PurchasePayableInstallment, SupplierPayment, SupplierPaymentAllocation,
    PurchaseLandedCost, PurchaseLandedCostAllocation,
)


@admin.register(PurchaseCategory)
class PurchaseCategoryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "company", "active")
    list_filter = ("company", "active")
    search_fields = ("code", "name")


class PurchaseDocumentLineInline(admin.TabularInline):
    model = PurchaseDocumentLine
    extra = 0


@admin.register(PurchaseDocument)
class PurchaseDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "document_type",
        "series",
        "number",
        "supplier",
        "issue_date",
        "payment_method",
        "document_status",
        "payment_status",
        "total",
    )
    list_filter = ("company", "document_status", "payment_status", "payment_method", "currency")
    search_fields = ("series", "number", "supplier_name", "supplier_document_number")
    inlines = (PurchaseDocumentLineInline,)


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 0


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "supplier", "order_date", "expected_date", "status", "total")
    list_filter = ("company", "status", "currency")
    search_fields = ("order_number", "supplier__name", "supplier__document_number")
    inlines = (PurchaseOrderLineInline,)


class PurchaseReceiptLineInline(admin.TabularInline):
    model = PurchaseReceiptLine
    extra = 0


@admin.register(PurchaseReceipt)
class PurchaseReceiptAdmin(admin.ModelAdmin):
    list_display = ("receipt_number", "purchase_order", "warehouse", "receipt_date", "status")
    list_filter = ("status", "warehouse__store")
    search_fields = ("receipt_number", "purchase_order__order_number", "purchase_order__supplier__name")
    inlines = (PurchaseReceiptLineInline,)


class SupplierPaymentAllocationInline(admin.TabularInline):
    model = SupplierPaymentAllocation
    extra = 0


@admin.register(SupplierPayment)
class SupplierPaymentAdmin(admin.ModelAdmin):
    list_display = ("payment_number", "supplier", "payment_date", "currency", "amount", "status")
    list_filter = ("company", "store", "status", "currency", "means_of_payment")
    search_fields = ("payment_number", "supplier__name", "reference")
    inlines = (SupplierPaymentAllocationInline,)


@admin.register(PurchasePayableInstallment)
class PurchasePayableInstallmentAdmin(admin.ModelAdmin):
    list_display = ("purchase_document", "sequence", "due_date", "amount")
    search_fields = ("purchase_document__series", "purchase_document__number", "purchase_document__supplier_name")


class PurchaseLandedCostAllocationInline(admin.TabularInline):
    model = PurchaseLandedCostAllocation
    extra = 0


@admin.register(PurchaseLandedCost)
class PurchaseLandedCostAdmin(admin.ModelAdmin):
    list_display = ("description", "purchase_document", "amount", "allocation_method", "status")
    list_filter = ("status", "allocation_method", "purchase_document__company")
    search_fields = ("description", "reference", "purchase_document__series", "purchase_document__number")
    inlines = (PurchaseLandedCostAllocationInline,)
