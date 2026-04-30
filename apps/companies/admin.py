from django.contrib import admin

from .models import Company, Store, UserCompanyAccess


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "trade_name", "is_active")
    search_fields = ("name", "trade_name", "document_number")


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "name", "code", "is_active")
    list_filter = ("company", "is_active")
    search_fields = ("name", "code")


@admin.register(UserCompanyAccess)
class UserCompanyAccessAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "company", "store", "is_default")
    list_filter = ("company", "is_default")
