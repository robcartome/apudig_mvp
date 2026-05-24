from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Employee, Permission, Role, RolePermission, User, UserOperationalFlags, UserRole, UserStore


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
    list_display = ("name", "description", "created_at")
    search_fields = ("name",)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "action_name", "module", "description")
    list_filter = ("action_name", "module")
    search_fields = ("code", "description", "module")


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "permission")
    list_filter = ("role",)


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "company", "created_at")
    list_filter = ("role", "company")


@admin.register(UserOperationalFlags)
class UserOperationalFlagsAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "is_operation_admin", "is_seller_profile", "can_close_purchase_order")
    list_filter = ("company", "is_operation_admin", "is_seller_profile")
    search_fields = ("user__email", "user__name")


@admin.register(UserStore)
class UserStoreAdmin(admin.ModelAdmin):
    list_display = ("user", "store", "role", "is_active")
    list_filter = ("role", "is_active")


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("full_name", "company", "document_number", "is_active")
    list_filter = ("company", "is_active")
    search_fields = ("first_name", "last_name", "document_number")
