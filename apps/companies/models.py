from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Company(TimeStampedModel):
    name = models.CharField(max_length=200)
    trade_name = models.CharField(max_length=200, blank=True)
    document_number = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "companies"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.trade_name or self.name


class Store(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="stores")
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "stores"
        ordering = ["company_id", "name"]
        unique_together = ("company", "code")

    def __str__(self) -> str:
        return f"{self.company} - {self.name}"


class UserCompanyAccess(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="company_accesses")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="user_accesses")
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="user_accesses", null=True, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "user_companies"
        unique_together = ("user", "company", "store")

    def __str__(self) -> str:
        return f"{self.user} -> {self.company}"
