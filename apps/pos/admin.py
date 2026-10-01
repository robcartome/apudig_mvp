from django.contrib import admin

from .models import (
    CashDenominationCount,
    CashMovement,
    CashSession,
    CashTenderDeclaration,
    PosRegister,
    PosRefundPayment,
    PosReturn,
    PosReturnLine,
    PosTransaction,
    SalesDocumentSource,
    SalesPayment,
)


@admin.register(PosRegister)
class PosRegisterAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "store", "active", "current_ticket_number")
    list_filter = ("company", "store", "active")
    search_fields = ("code", "name")


@admin.register(CashSession)
class CashSessionAdmin(admin.ModelAdmin):
    list_display = ("register", "status", "opened_at", "opened_by", "closed_at", "cash_difference")
    list_filter = ("status", "company", "store")
    readonly_fields = ("created_at", "updated_at")


@admin.register(PosTransaction)
class PosTransactionAdmin(admin.ModelAdmin):
    list_display = ("ticket_code", "register", "status", "billing_status", "cashier", "started_at")
    list_filter = ("status", "billing_status", "company", "store")
    search_fields = ("ticket_code", "sales_document__number")


admin.site.register(CashDenominationCount)
admin.site.register(CashMovement)
admin.site.register(CashTenderDeclaration)
admin.site.register(SalesPayment)
admin.site.register(SalesDocumentSource)
admin.site.register(PosReturn)
admin.site.register(PosReturnLine)
admin.site.register(PosRefundPayment)
