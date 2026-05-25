from django.contrib import admin

from .models import Carrier, Customer, DocumentType, SalesCustomerContact, SalesCustomerProfile, Supplier


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "abbreviation", "active")
    search_fields = ("code", "name")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("document_number", "legal_name", "document_type", "phone", "email", "active")
    list_filter = ("document_type", "active")
    search_fields = ("document_number", "legal_name", "trade_name")


@admin.register(SalesCustomerProfile)
class SalesCustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("customer", "payment_term_days", "is_retention_agent", "active")
    list_filter = ("active", "is_retention_agent")


@admin.register(SalesCustomerContact)
class SalesCustomerContactAdmin(admin.ModelAdmin):
    list_display = ("name", "customer", "phone", "email", "position")
    search_fields = ("name", "customer__legal_name")


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "document_number", "phone", "email", "active")
    list_filter = ("active",)
    search_fields = ("name", "document_number")


@admin.register(Carrier)
class CarrierAdmin(admin.ModelAdmin):
    list_display = ("business_name", "document_number", "license_plate", "driver_name", "active")
    list_filter = ("active",)
    search_fields = ("business_name", "document_number")
