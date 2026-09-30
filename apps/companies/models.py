import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.managers import CompanyScopedManager, CompanyScopedQuerySet
from apps.core.models import TimeStampedModel


class UserCompanyAccessQuerySet(CompanyScopedQuerySet):
    def for_user(self, user):
        return self.filter(user=user)

    def selectable(self):
        """Hide company-level access when the user has store-level access."""
        companies_with_store_access = self.filter(
            store__isnull=False,
        ).values_list("company_id", flat=True)
        return self.exclude(
            store__isnull=True,
            company_id__in=companies_with_store_access,
        )


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


class TaxRate(TimeStampedModel):
    """Versioned fiscal rule used to resolve taxes for new operations.

    Commercial documents keep their own tax snapshots; changing a rule never
    changes an already created document.
    """

    AFFECTATION_CHOICES = [
        ("10", "Gravado IGV"),
        ("20", "Exonerado"),
        ("30", "Inafecto"),
        ("40", "Exportacion"),
        ("11", "Operacion gratuita"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="tax_rates")
    country_code = models.CharField(max_length=2, default="PE")
    code = models.CharField(max_length=30, default="IGV_GENERAL_PE")
    name = models.CharField(max_length=100, default="IGV general")
    affectation_type = models.CharField(max_length=5, choices=AFFECTATION_CHOICES, default="10")
    rate = models.DecimalField(max_digits=5, decimal_places=2)
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "tax_rates"
        ordering = ("-valid_from", "code")
        constraints = [
            models.UniqueConstraint(
                fields=("company", "code", "affectation_type", "valid_from"),
                name="uniq_company_tax_rule_from",
            ),
            models.CheckConstraint(condition=models.Q(rate__gte=0), name="tax_rate_gte_zero"),
            models.CheckConstraint(
                condition=models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=models.F("valid_from")),
                name="tax_rate_valid_period",
            ),
            models.UniqueConstraint(
                fields=("company", "affectation_type"),
                condition=models.Q(active=True, is_default=True, valid_until__isnull=True),
                name="uniq_current_default_tax_affectation",
            ),
        ]

    def __str__(self):
        return f"{self.company} / {self.name} {self.rate}%"


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
        constraints = [
            models.UniqueConstraint(
                fields=("user", "company"),
                condition=models.Q(store__isnull=True),
                name="uniq_user_company_without_store",
            ),
        ]

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

    class PosProductSearchMode(models.TextChoices):
        SEARCH = "SEARCH", "Buscador rápido"
        CATALOG = "CATALOG", "Catálogo visual por tarjetas"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.OneToOneField(
        Company, on_delete=models.CASCADE, related_name="operational_settings"
    )

    inventory_quantity_editable = models.BooleanField(default=True)
    inventory_unit_cost_editable = models.BooleanField(default=True)
    inventory_allow_negative_stock = models.BooleanField(default=False)
    sales_value_unit_editable = models.BooleanField(default=False)
    sales_price_unit_editable = models.BooleanField(default=True)
    sales_total_editable = models.BooleanField(default=False)
    purchases_value_unit_editable = models.BooleanField(default=True)
    purchases_price_unit_editable = models.BooleanField(default=True)
    purchases_total_editable = models.BooleanField(default=False)
    pos_product_search_mode = models.CharField(
        max_length=10,
        choices=PosProductSearchMode.choices,
        default=PosProductSearchMode.SEARCH,
    )
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

