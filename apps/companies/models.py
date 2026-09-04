import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.managers import CompanyScopedManager, CompanyScopedQuerySet
from apps.core.models import TimeStampedModel


class UserCompanyAccessQuerySet(CompanyScopedQuerySet):
    def for_user(self, user):
        return self.filter(user=user)


class UserCompanyAccessManager(CompanyScopedManager):
    def get_queryset(self):
        return UserCompanyAccessQuerySet(self.model, using=self._db)

    def for_user(self, user):
        return self.get_queryset().for_user(user)


class Company(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    ruc = models.CharField(max_length=15, unique=True)
    address = models.CharField(max_length=500, blank=True)
    email = models.EmailField(max_length=255, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "companies"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class CompanyBranding(TimeStampedModel):
    """company_branding — identidad visual, relación 1:1 con Company."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.OneToOneField(
        Company, on_delete=models.CASCADE, related_name="branding"
    )
    app_logo_url = models.CharField(max_length=1000, blank=True)
    pdf_logo_url = models.CharField(max_length=1000, blank=True)
    primary_color = models.CharField(max_length=20, blank=True, default="#066fd1")
    secondary_color = models.CharField(max_length=20, blank=True, default="#4a4a4a")

    class Meta:
        db_table = "company_branding"

    def __str__(self) -> str:
        return f"Branding – {self.company}"


class Store(TimeStampedModel):
    objects = CompanyScopedManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="stores")
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500, blank=True)
    active = models.BooleanField(default=True)
    lock_movement_edits = models.BooleanField(default=True)

    class Meta:
        db_table = "stores"
        ordering = ["company_id", "name"]

    def __str__(self) -> str:
        return f"{self.company} - {self.name}"


class UserCompanyAccess(TimeStampedModel):
    """Tabla auxiliar de sesión para seleccionar empresa/sucursal activa."""

    objects = UserCompanyAccessManager()
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


class CompanyDocumentSettings(TimeStampedModel):
    """company_document_settings - configuración de formato y plantilla PDF por tipo de documento."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="document_settings")
    document_type = models.CharField(max_length=30)          # '01', '03', 'COT', etc.
    format = models.CharField(max_length=20, default="A4")   # 'A4', 'TICKET', etc.
    template_name = models.CharField(max_length=100, blank=True)
    logo_url_override = models.CharField(max_length=1000, blank=True)
    footer_text = models.TextField(blank=True)

    class Meta:
        db_table = "company_document_settings"
        unique_together = ("company", "document_type")

    def __str__(self) -> str:
        return f"{self.company} / {self.document_type}"


class CompanyOperationalSettings(TimeStampedModel):
    """Preferencias operativas que se aplican a todos los locales de una empresa."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.OneToOneField(
        Company, on_delete=models.CASCADE, related_name="operational_settings"
    )

    inventory_quantity_editable = models.BooleanField(default=True)
    inventory_unit_cost_editable = models.BooleanField(default=True)
    sales_value_unit_editable = models.BooleanField(default=False)
    sales_price_unit_editable = models.BooleanField(default=True)
    sales_total_editable = models.BooleanField(default=False)
    purchases_value_unit_editable = models.BooleanField(default=True)
    purchases_price_unit_editable = models.BooleanField(default=True)
    purchases_total_editable = models.BooleanField(default=False)
    price_decimal_places = models.PositiveSmallIntegerField(default=2)
    default_igv_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("18.00")
    )

    default_customer = models.ForeignKey(
        "partners.Customer", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="default_for_company_settings",
    )
    default_supplier = models.ForeignKey(
        "partners.Supplier", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="default_for_company_settings",
    )
    default_sales_document_type = models.ForeignKey(
        "partners.DocumentType", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="default_sales_for_companies",
    )
    default_purchase_document_type = models.ForeignKey(
        "partners.DocumentType", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="default_purchase_for_companies",
    )
    default_sales_payment_method = models.ForeignKey(
        "sales.PaymentMethod", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="default_sales_for_companies",
    )
    default_purchase_payment_method = models.ForeignKey(
        "sales.PaymentMethod", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="default_purchases_for_companies",
    )

    class Meta:
        db_table = "company_operational_settings"

    def __str__(self) -> str:
        return f"Configuracion operativa - {self.company}"

