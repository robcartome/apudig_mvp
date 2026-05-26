from django.urls import path

from .views import (
    admin_panel,
    company_create,
    company_delete,
    company_edit,
    company_list,
    configuracion,
    permission_create,
    permission_delete,
    permission_list,
    role_create,
    role_delete,
    role_edit,
    role_list,
    role_permissions,
    store_create,
    store_delete,
    store_edit,
    user_create,
    user_delete,
    user_detail,
    user_list,
)

app_name = "users"

urlpatterns = [
    # Panel raíz → redirige a usuarios
    path("", admin_panel, name="admin_panel"),

    # ── Users ─────────────────────────────────────────────────────────────
    path("users/", user_list, name="user_list"),
    path("users/new/", user_create, name="user_create"),
    path("users/<uuid:pk>/", user_detail, name="user_detail"),
    path("users/<uuid:pk>/delete/", user_delete, name="user_delete"),

    # ── Roles ─────────────────────────────────────────────────────────────
    path("roles/", role_list, name="role_list"),
    path("roles/new/", role_create, name="role_create"),
    path("roles/<uuid:pk>/edit/", role_edit, name="role_edit"),
    path("roles/<uuid:pk>/permissions/", role_permissions, name="role_permissions"),
    path("roles/<uuid:pk>/delete/", role_delete, name="role_delete"),

    # ── Permissions (catalogue) ────────────────────────────────────────────
    path("permissions/", permission_list, name="permission_list"),
    path("permissions/new/", permission_create, name="permission_create"),
    path("permissions/<uuid:pk>/delete/", permission_delete, name="permission_delete"),

    # ── Companies ─────────────────────────────────────────────────────────
    path("companies/", company_list, name="company_list"),
    path("companies/new/", company_create, name="company_create"),
    path("companies/<uuid:pk>/edit/", company_edit, name="company_edit"),
    path("companies/<uuid:pk>/delete/", company_delete, name="company_delete"),

    # ── Branches (within a company) ───────────────────────────────────────
    path("companies/<uuid:company_pk>/branches/new/", store_create, name="store_create"),
    path("companies/<uuid:company_pk>/branches/<uuid:pk>/edit/", store_edit, name="store_edit"),
    path("companies/<uuid:company_pk>/branches/<uuid:pk>/delete/", store_delete, name="store_delete"),

    # ── Settings ──────────────────────────────────────────────────────────
    path("settings/", configuracion, name="configuracion"),
]

