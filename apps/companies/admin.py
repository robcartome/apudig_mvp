from django.contrib import admin

from .models import Company, CompanyDocumentSettings, Store, UserCompanyAccess


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "ruc", "is_active")
    search_fields = ("name", "ruc")


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "name", "active")
    list_filter = ("company", "active")
    search_fields = ("name",)


@admin.register(UserCompanyAccess)
class UserCompanyAccessAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "company", "store", "is_default")
    list_filter = ("company", "is_default")


@admin.register(CompanyDocumentSettings)
class CompanyDocumentSettingsAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "document_type", "format", "template_name")
    list_filter = ("company",)
    search_fields = ("document_type",)
