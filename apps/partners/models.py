import uuid

from django.db import models
from apps.core.managers import CompanyScopedManager
from apps.core.models import TimeStampedModel


class SalesCustomerContactQuerySet(models.QuerySet):
    def for_company(self, company_id):
        return self.filter(customer__company_id=company_id)


class SalesCustomerContactManager(models.Manager):
    def get_queryset(self):
        return SalesCustomerContactQuerySet(self.model, using=self._db)

    def for_company(self, company_id):
        return self.get_queryset().for_company(company_id)


class DocumentType(models.Model):
    """document_types - tipos de documento de identidad (DNI, RUC, CE, etc.)"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=5, unique=True)
    name = models.CharField(max_length=100)
    abbreviation = models.CharField(max_length=10)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "document_types"
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class Customer(TimeStampedModel):
    """customers - cliente canónico (source of truth)"""

    objects = CompanyScopedManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE,
        related_name="customers", null=True, blank=True,
    )
    document_type = models.CharField(max_length=2)  # 6=RUC, 1=DNI, etc.
    document_number = models.CharField(max_length=20)
    legal_name = models.CharField(max_length=300)
    trade_name = models.CharField(max_length=300, blank=True)
    address = models.CharField(max_length=500, blank=True)
    ubigeo = models.CharField(max_length=6, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.CharField(max_length=200, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "customers"
        ordering = ["legal_name"]
        unique_together = (("company", "document_type", "document_number"),)

    def __str__(self) -> str:
        return f"{self.document_number} - {self.legal_name}"


class SalesCustomerProfile(TimeStampedModel):
    """sales_customer_profiles - perfil comercial del cliente"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name="sales_profile")
    taxpayer_status = models.CharField(max_length=40, blank=True)
    taxpayer_condition = models.CharField(max_length=20, blank=True)
    is_retention_agent = models.BooleanField(default=False)
    payment_term_days = models.IntegerField(default=0)
    price_list = models.ForeignKey(
        "inventory.PriceList", on_delete=models.SET_NULL, null=True, blank=True, related_name="customer_profiles"
    )
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "sales_customer_profiles"


class SalesCustomerContact(models.Model):
    """sales_customer_contacts"""

    objects = SalesCustomerContactManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey("Customer", on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30, blank=True)
    email = models.CharField(max_length=200, blank=True)
    position = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "sales_customer_contacts"

    def __str__(self) -> str:
        return f"{self.name} ({self.customer})"


class Supplier(TimeStampedModel):
    """suppliers"""

    objects = CompanyScopedManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE,
        related_name="suppliers", null=True, blank=True,
    )
    name = models.CharField(max_length=255)
    document_number = models.CharField(max_length=20)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.CharField(max_length=120, blank=True)
    contact_name = models.CharField(max_length=120, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "suppliers"
        ordering = ["name"]
        unique_together = (("company", "document_number"),)

    def __str__(self) -> str:
        return self.name


class Carrier(TimeStampedModel):
    """carriers - transportistas"""

    objects = CompanyScopedManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE,
        related_name="carriers", null=True, blank=True,
    )
    business_name = models.CharField(max_length=255)
    document_number = models.CharField(max_length=11)
    license_plate = models.CharField(max_length=20, blank=True)
    driver_name = models.CharField(max_length=120, blank=True)
    driver_license = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "carriers"
        ordering = ["business_name"]
        unique_together = (("company", "document_number"),)

    def __str__(self) -> str:
        return self.business_name
