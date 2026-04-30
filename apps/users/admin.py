from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Employee, Permission, Role, RolePermission, User, UserRole, UserStore


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "name", "is_active", "is_staff", "created_at")
    list_filter = ("is_active", "is_staff", "is_superuser")
    search_fields = ("email", "name")
    ordering = ("email",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Información personal", {"fields": ("name", "phone")}),
        ("Permisos", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "name", "password1", "password2")}),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "description")
    search_fields = ("code",)


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "company")
    list_filter = ("role", "company")


@admin.register(UserStore)
class UserStoreAdmin(admin.ModelAdmin):
    list_display = ("user", "store", "role", "is_active")
    list_filter = ("role", "is_active")


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("full_name", "company", "document_number", "is_active")
    list_filter = ("company", "is_active")
    search_fields = ("first_name", "last_name", "document_number")


admin.site.register(RolePermission)
