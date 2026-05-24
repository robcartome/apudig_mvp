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

    # ── Usuarios ──────────────────────────────────────────────────────────
    path("usuarios/", user_list, name="user_list"),
    path("usuarios/nuevo/", user_create, name="user_create"),
    path("usuarios/<uuid:pk>/", user_detail, name="user_detail"),
    path("usuarios/<uuid:pk>/eliminar/", user_delete, name="user_delete"),

    # ── Roles ─────────────────────────────────────────────────────────────
    path("roles/", role_list, name="role_list"),
    path("roles/nuevo/", role_create, name="role_create"),
    path("roles/<uuid:pk>/editar/", role_edit, name="role_edit"),
    path("roles/<uuid:pk>/permisos/", role_permissions, name="role_permissions"),
    path("roles/<uuid:pk>/eliminar/", role_delete, name="role_delete"),

    # ── Permisos (catálogo) ────────────────────────────────────────────────
    path("permisos/", permission_list, name="permission_list"),
    path("permisos/nuevo/", permission_create, name="permission_create"),
    path("permisos/<uuid:pk>/eliminar/", permission_delete, name="permission_delete"),

    # ── Empresas ──────────────────────────────────────────────────────────
    path("empresas/", company_list, name="company_list"),
    path("empresas/nueva/", company_create, name="company_create"),
    path("empresas/<uuid:pk>/editar/", company_edit, name="company_edit"),
    path("empresas/<uuid:pk>/eliminar/", company_delete, name="company_delete"),

    # ── Sucursales (dentro de una empresa) ────────────────────────────────
    path("empresas/<uuid:company_pk>/sucursales/nueva/", store_create, name="store_create"),
    path("empresas/<uuid:company_pk>/sucursales/<uuid:pk>/editar/", store_edit, name="store_edit"),
    path("empresas/<uuid:company_pk>/sucursales/<uuid:pk>/eliminar/", store_delete, name="store_delete"),

    # ── Configuración ─────────────────────────────────────────────────────
    path("configuracion/", configuracion, name="configuracion"),
]

