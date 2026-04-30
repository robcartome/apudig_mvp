import uuid

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Company(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    ruc = models.CharField(max_length=15, unique=True)
    is_active = models.BooleanField(default=True)

    # branding agregado inline (simplificado)
    app_logo_url = models.CharField(max_length=1000, blank=True)
    pdf_logo_url = models.CharField(max_length=1000, blank=True)
    primary_color = models.CharField(max_length=20, blank=True)
    secondary_color = models.CharField(max_length=20, blank=True)

    class Meta:
        db_table = "companies"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Store(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="stores")
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "stores"
        ordering = ["company_id", "name"]

    def __str__(self) -> str:
        return f"{self.company} - {self.name}"


class UserCompanyAccess(TimeStampedModel):
    """Tabla auxiliar de sesión para seleccionar empresa/sucursal activa."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="company_accesses")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="user_accesses")
    store = models.ForeignKey(Store, on_delete=models.SET_NULL, null=True, blank=True, related_name="user_accesses")
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "user_companies"
        unique_together = ("user", "company", "store")

    def __str__(self) -> str:
        return f"{self.user} -> {self.company}"
