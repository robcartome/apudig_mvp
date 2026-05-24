from django.urls import path

from .views import (
    admin_panel,
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

    # ── Configuración ─────────────────────────────────────────────────────
    path("configuracion/", configuracion, name="configuracion"),
]

