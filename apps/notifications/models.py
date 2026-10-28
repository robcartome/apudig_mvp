import uuid

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class NotificationType(models.TextChoices):
    PURCHASE_DUE = "PURCHASE_DUE", "Vencimiento de compra"


class NotificationPriority(models.TextChoices):
    INFO = "INFO", "Informativa"
    WARNING = "WARNING", "Atención"
    HIGH = "HIGH", "Urgente"


class Notification(TimeStampedModel):
    """Persistent business event; financial entities remain the source of truth."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE, related_name="notifications"
    )
    store = models.ForeignKey(
        "companies.Store", on_delete=models.CASCADE, related_name="notifications"
    )
    notification_type = models.CharField(max_length=40, choices=NotificationType.choices)
    priority = models.CharField(
        max_length=20, choices=NotificationPriority.choices,
        default=NotificationPriority.INFO,
    )
    title = models.CharField(max_length=180)
    message = models.CharField(max_length=500)
    source_type = models.CharField(max_length=100)
    source_id = models.CharField(max_length=64)
    deduplication_key = models.CharField(max_length=180)
    target_url = models.CharField(max_length=500)
    due_date = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications"
        ordering = ("-priority", "due_date", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("company", "store", "deduplication_key"),
                name="uniq_notification_scope_dedup_key",
            ),
        ]
        indexes = [
            models.Index(
                fields=("company", "store", "is_active", "notification_type"),
                name="notif_scope_active_type_idx",
            ),
            models.Index(
                fields=("source_type", "source_id"), name="notif_source_idx"
            ),
        ]


class NotificationRecipient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE, related_name="recipients"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_recipients",
    )
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification_recipients"
        constraints = [
            models.UniqueConstraint(
                fields=("notification", "user"),
                name="uniq_notification_recipient_user",
            ),
        ]
        indexes = [
            models.Index(fields=("user", "read_at"), name="notif_recipient_read_idx"),
        ]

