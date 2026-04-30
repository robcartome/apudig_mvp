import uuid

from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditLog(models.Model):
    """Auditoría básica de acciones sobre entidades del sistema."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=100)           # CREATE, UPDATE, DELETE, LOGIN, etc.
    entity = models.CharField(max_length=100, blank=True)   # 'Product', 'Voucher', etc.
    entity_id = models.CharField(max_length=255, blank=True) # UUID o int del objeto afectado
    meta_data = models.JSONField(null=True, blank=True)      # detalles extra si se necesitan
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} / {self.entity} ({self.entity_id}) by {self.user_id}"
