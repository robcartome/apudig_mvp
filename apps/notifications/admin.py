from django.contrib import admin

from .models import Notification, NotificationRecipient


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "title", "company", "store", "notification_type", "priority",
        "is_active", "due_date", "updated_at",
    )
    list_filter = ("notification_type", "priority", "is_active")
    search_fields = ("title", "message", "deduplication_key", "source_id")


@admin.register(NotificationRecipient)
class NotificationRecipientAdmin(admin.ModelAdmin):
    list_display = ("notification", "user", "read_at", "created_at")
    list_filter = ("read_at",)
    search_fields = ("user__email", "notification__title")

