from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "entity", "entity_id")
    list_filter = ("action", "entity")
    search_fields = ("entity_id", "user__email")
    readonly_fields = ("id", "user", "action", "entity", "entity_id", "meta_data", "created_at")
