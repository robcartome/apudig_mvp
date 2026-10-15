from django.contrib import admin

from .models import (
    Bank, BankAccount, BankMovement, CashSafeCount, CashSafeDeposit, CashSafeMovement,
    CashSafeMovementAttachment,
)


@admin.register(CashSafeMovement)
class CashSafeMovementAdmin(admin.ModelAdmin):
    list_display = (
        "movement_number", "store", "movement_type", "status",
        "currency", "amount", "created_at",
    )
    list_filter = ("company", "store", "currency", "direction", "status", "movement_type")
    search_fields = ("movement_number", "recipient_name", "destination", "reference")
    readonly_fields = (
        "movement_number", "created_at", "updated_at", "reversed_at", "reversed_movement",
    )


admin.site.register(Bank)
admin.site.register(BankAccount)
admin.site.register(BankMovement)
admin.site.register(CashSafeCount)
admin.site.register(CashSafeDeposit)
admin.site.register(CashSafeMovementAttachment)
