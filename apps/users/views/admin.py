"""
users/views/admin.py — Vistas del panel de administración (Usuarios, Roles, Empresas).
"""
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.companies.models import Company, CompanyBranding, Store, UserCompanyAccess
from apps.users.forms import (
    CompanyAdminForm,
    CompanyBrandingAdminForm,
    PermissionForm,
    RoleForm,
    SetPasswordForm,
    StoreAdminForm,
    UserCreateForm,
    UserEditForm,
    UserOperationalFlagsForm,
)
from apps.users.models import (
    Permission,
    Role,
    RolePermission,
    UserOperationalFlags,
    UserRole,
)

User = get_user_model()


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _staff_required(request):
    """Returns (ok, response|None). If not staff, returns (False, redirect/403)."""
    if not request.user.is_authenticated:
        return False, redirect("login")
    if not request.user.is_staff:
        return False, HttpResponseForbidden("Acceso restringido al personal de administración.")
    return True, None


def _get_active_company(request):
    company_id = request.session.get("active_company_id")
    if company_id:
        return Company.objects.filter(pk=company_id).first()
    return None


# ─────────────────────────────────────────────
# Panel raíz
# ─────────────────────────────────────────────

@login_required
def admin_panel(request):
    ok, err = _staff_required(request)
    if not ok:
        return err
    return redirect("users:user_list")


# ─────────────────────────────────────────────
# Gestión de Usuarios
# ─────────────────────────────────────────────

@login_required
def user_list(request):
    ok, err = _staff_required(request)
    if not ok:
        return err

    company = _get_active_company(request)
    search = request.GET.get("q", "").strip()

    if request.user.is_superuser:
        # Superadmin siempre ve todos los usuarios del sistema.
        qs = User.objects.all()
    elif company:
        # Usuarios visibles por empresa activa:
        # - con roles en la empresa
        # - o con acceso explícito a la empresa (user_companies)
        role_user_ids = UserRole.objects.filter(company=company).values_list("user_id", flat=True)
        company_access_user_ids = UserCompanyAccess.objects.filter(company=company).values_list("user_id", flat=True)
        qs = User.objects.filter(Q(id__in=role_user_ids) | Q(id__in=company_access_user_ids)).distinct()

        # Evita el caso confuso de quedar sin ningún usuario visible estando logueado.
        if not qs.exists() and request.user.is_authenticated:
            qs = User.objects.filter(pk=request.user.pk)
    else:
        # Sin empresa activa, un admin no-super solo debe verse a sí mismo.
        qs = User.objects.filter(pk=request.user.pk)

    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(email__icontains=search))

    qs = qs.order_by("name", "email")

    # Enriquecer con datos de empresa y roles
    users_data = []
    for u in qs:
        company_count = UserCompanyAccess.objects.filter(user=u).values("company").distinct().count()
        roles = []
        if company:
            roles = list(
                UserRole.objects.filter(user=u, company=company)
                .select_related("role")
                .values_list("role__name", flat=True)
            )
        users_data.append({
            "user": u,
            "company_count": company_count,
            "roles": roles,
        })

    return render(request, "admin_panel/user_list.html", {
        "users_data": users_data,
        "active_tab": "usuarios",
        "search": search,
        "active_company": company,
    })


@login_required
def user_create(request):
    ok, err = _staff_required(request)
    if not ok:
        return err

    company = _get_active_company(request)

    if not request.user.is_superuser and not company:
        messages.error(request, "Debes seleccionar una empresa activa antes de crear usuarios.")
        return redirect("select_company")

    form = UserCreateForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save()
            # Asignar acceso a la empresa activa automáticamente
            if company:
                from apps.companies.models import UserCompanyAccess
                UserCompanyAccess.objects.get_or_create(
                    user=user,
                    company=company,
                    defaults={"is_default": True},
                )
        messages.success(request, f"Usuario '{user.email}' creado correctamente.")
        return redirect("users:user_detail", pk=user.pk)

    return render(request, "admin_panel/user_form.html", {
        "form": form,
        "active_tab": "usuarios",
        "title": "Crear usuario",
        "submit_label": "Crear usuario",
    })


@login_required
def user_detail(request, pk):
    ok, err = _staff_required(request)
    if not ok:
        return err

    target = get_object_or_404(User, pk=pk)
    company = _get_active_company(request)
    tab = request.GET.get("tab", "general")

    # Formulario de edición general
    edit_form = UserEditForm(request.POST if request.method == "POST" and "save_general" in request.POST else None, instance=target)
    if request.method == "POST" and "save_general" in request.POST:
        if edit_form.is_valid():
            edit_form.save()
            messages.success(request, "Información actualizada.")
            return redirect(f"{request.path}?tab=general")

    # Formulario de contraseña
    pw_form = SetPasswordForm(request.POST if request.method == "POST" and "save_password" in request.POST else None)
    if request.method == "POST" and "save_password" in request.POST:
        if pw_form.is_valid():
            target.set_password(pw_form.cleaned_data["password1"])
            target.save(update_fields=["password"])
            messages.success(request, "Contraseña actualizada.")
            return redirect(f"{request.path}?tab=general")

    # Flags operativos
    flags_obj = None
    flags_form = None
    if company:
        flags_obj, _ = UserOperationalFlags.objects.get_or_create(user=target, company=company)
        flags_form = UserOperationalFlagsForm(
            request.POST if request.method == "POST" and "save_flags" in request.POST else None,
            instance=flags_obj,
        )
        if request.method == "POST" and "save_flags" in request.POST:
            if flags_form.is_valid():
                flags_form.save()
                messages.success(request, "Permisos operativos actualizados.")
                return redirect(f"{request.path}?tab=operativos")

    # Roles del usuario en empresa activa
    assigned_roles = []
    available_roles = []
    if company:
        assigned_role_ids = UserRole.objects.filter(user=target, company=company).values_list("role_id", flat=True)
        assigned_roles = list(Role.objects.filter(id__in=assigned_role_ids))
        available_roles = list(Role.objects.exclude(id__in=assigned_role_ids))

    # Guardar roles (POST desde tab roles)
    if request.method == "POST" and "save_roles" in request.POST and company:
        selected_ids = request.POST.getlist("role_ids")
        with transaction.atomic():
            # Eliminar roles no seleccionados
            UserRole.objects.filter(user=target, company=company).exclude(role_id__in=selected_ids).delete()
            # Agregar nuevos
            for role_id in selected_ids:
                role = Role.objects.filter(pk=role_id).first()
                if role:
                    UserRole.objects.get_or_create(user=target, role=role, company=company)
        messages.success(request, "Roles actualizados correctamente.")
        return redirect(f"{request.path}?tab=roles")

    # ── Tab: Empresas y Sucursales (accesos) ──────────────────────────────
    # Solo superusuarios pueden gestionar los accesos de otros usuarios
    accesos_por_empresa = []
    if request.user.is_superuser:
        user_access_pairs = set(
            UserCompanyAccess.objects.filter(user=target)
            .values_list("company_id", "store_id")
        )
        # Normalizar: store_id None queda como None, UUID como str
        user_access_set = {
            (str(c), str(s) if s else None)
            for c, s in user_access_pairs
        }
        for co in Company.objects.filter(is_active=True).prefetch_related("stores").order_by("name"):
            stores_info = [
                {
                    "store": st,
                    "has_access": (str(co.pk), str(st.pk)) in user_access_set,
                }
                for st in co.stores.filter(active=True).order_by("name")
            ]
            accesos_por_empresa.append({
                "company": co,
                "has_company_access": (str(co.pk), None) in user_access_set,
                "stores": stores_info,
            })

    if request.method == "POST" and "save_accesos" in request.POST and request.user.is_superuser:
        selected_pairs = request.POST.getlist("access")  # e.g. ["UUID|", "UUID|UUID"]
        desired: set[tuple[str, str | None]] = set()
        for item in selected_pairs:
            parts = item.split("|", 1)
            co_id = parts[0].strip()
            st_id = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
            if co_id:
                desired.add((co_id, st_id))

        with transaction.atomic():
            # Eliminar los accesos que ya no están seleccionados
            for access in UserCompanyAccess.objects.filter(user=target).select_related("company", "store"):
                key = (str(access.company_id), str(access.store_id) if access.store_id else None)
                if key not in desired:
                    access.delete()
            # Agregar los accesos nuevos
            for co_id, st_id in desired:
                co = Company.objects.filter(pk=co_id).first()
                if not co:
                    continue
                store = Store.objects.filter(pk=st_id, company=co).first() if st_id else None
                UserCompanyAccess.objects.get_or_create(
                    user=target,
                    company=co,
                    store=store,
                    defaults={"is_default": False},
                )
        messages.success(request, "Accesos a empresas/sucursales actualizados.")
        return redirect(f"{request.path}?tab=accesos")

    return render(request, "admin_panel/user_detail.html", {
        "target": target,
        "edit_form": edit_form,
        "pw_form": pw_form,
        "flags_form": flags_form,
        "assigned_roles": assigned_roles,
        "available_roles": available_roles,
        "accesos_por_empresa": accesos_por_empresa,
        "active_tab": "usuarios",
        "detail_tab": tab,
        "active_company": company,
    })


@login_required
def user_delete(request, pk):
    ok, err = _staff_required(request)
    if not ok:
        return err

    target = get_object_or_404(User, pk=pk)

    if target == request.user:
        messages.error(request, "No puedes eliminar tu propia cuenta.")
        return redirect("users:user_list")

    if request.method == "POST":
        email = target.email
        target.delete()
        messages.success(request, f"Usuario '{email}' eliminado.")
        return redirect("users:user_list")

    return render(request, "admin_panel/user_confirm_delete.html", {
        "target": target,
        "active_tab": "usuarios",
    })


# ─────────────────────────────────────────────
# Gestión de Roles
# ─────────────────────────────────────────────

@login_required
def role_list(request):
    ok, err = _staff_required(request)
    if not ok:
        return err

    roles = Role.objects.annotate(
        user_count=Count("user_roles", distinct=True),
        permission_count=Count("role_permissions", distinct=True),
    ).order_by("name")

    return render(request, "admin_panel/role_list.html", {
        "roles": roles,
        "active_tab": "roles",
    })


@login_required
def role_create(request):
    ok, err = _staff_required(request)
    if not ok:
        return err

    form = RoleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        role = form.save()
        messages.success(request, f"Rol '{role.name}' creado.")
        return redirect("users:role_permissions", pk=role.pk)

    return render(request, "admin_panel/role_form.html", {
        "form": form,
        "active_tab": "roles",
        "title": "Crear rol",
        "submit_label": "Crear rol",
    })


@login_required
def role_edit(request, pk):
    ok, err = _staff_required(request)
    if not ok:
        return err

    role = get_object_or_404(Role, pk=pk)
    form = RoleForm(request.POST or None, instance=role)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Rol actualizado.")
        return redirect("users:role_list")

    assigned = list(
        RolePermission.objects.filter(role=role)
        .select_related("permission")
        .values_list("permission_id", flat=True)
    )
    all_permissions = Permission.objects.all()

    return render(request, "admin_panel/role_form.html", {
        "form": form,
        "role": role,
        "active_tab": "roles",
        "title": f"Editar rol: {role.name}",
        "submit_label": "Guardar cambios",
    })


@login_required
def role_delete(request, pk):
    ok, err = _staff_required(request)
    if not ok:
        return err

    role = get_object_or_404(Role, pk=pk)
    if request.method == "POST":
        name = role.name
        role.delete()
        messages.success(request, f"Rol '{name}' eliminado.")
        return redirect("users:role_list")

    return render(request, "admin_panel/role_confirm_delete.html", {
        "role": role,
        "active_tab": "roles",
    })


@login_required
def role_permissions(request, pk):
    """Gestión de permisos asignados a un rol (dual-list)."""
    ok, err = _staff_required(request)
    if not ok:
        return err

    role = get_object_or_404(Role, pk=pk)
    assigned_ids = set(
        RolePermission.objects.filter(role=role).values_list("permission_id", flat=True)
    )
    all_permissions = Permission.objects.all().order_by("module", "action_name")
    assigned_perms = [p for p in all_permissions if p.id in assigned_ids]
    available_perms = [p for p in all_permissions if p.id not in assigned_ids]

    if request.method == "POST":
        selected_ids = request.POST.getlist("permission_ids")
        with transaction.atomic():
            RolePermission.objects.filter(role=role).exclude(permission_id__in=selected_ids).delete()
            for perm_id in selected_ids:
                perm = Permission.objects.filter(pk=perm_id).first()
                if perm:
                    RolePermission.objects.get_or_create(role=role, permission=perm)
        messages.success(request, f"Permisos del rol '{role.name}' actualizados.")
        return redirect("users:role_permissions", pk=pk)

    return render(request, "admin_panel/role_permissions.html", {
        "role": role,
        "assigned_perms": assigned_perms,
        "available_perms": available_perms,
        "active_tab": "roles",
    })


# ─────────────────────────────────────────────
# Gestión de Permisos (catálogo)
# ─────────────────────────────────────────────

@login_required
def permission_list(request):
    ok, err = _staff_required(request)
    if not ok:
        return err

    permissions = Permission.objects.all().order_by("module", "action_name")
    # Agrupar por módulo
    by_module: dict = {}
    for p in permissions:
        key = p.module or "Sin módulo"
        by_module.setdefault(key, []).append(p)

    return render(request, "admin_panel/permission_list.html", {
        "by_module": by_module,
        "active_tab": "roles",
    })


@login_required
def permission_create(request):
    ok, err = _staff_required(request)
    if not ok:
        return err

    form = PermissionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        perm = form.save()
        messages.success(request, f"Permiso '{perm.code}' creado.")
        return redirect("users:permission_list")

    return render(request, "admin_panel/permission_form.html", {
        "form": form,
        "active_tab": "roles",
        "title": "Crear permiso",
        "submit_label": "Crear",
    })


@login_required
def permission_delete(request, pk):
    ok, err = _staff_required(request)
    if not ok:
        return err

    perm = get_object_or_404(Permission, pk=pk)
    if request.method == "POST":
        code = perm.code
        perm.delete()
        messages.success(request, f"Permiso '{code}' eliminado.")
        return redirect("users:permission_list")

    return render(request, "admin_panel/permission_confirm_delete.html", {
        "perm": perm,
        "active_tab": "roles",
    })


# ─────────────────────────────────────────────
# Gestión de Empresas
# ─────────────────────────────────────────────

@login_required
def company_list(request):
    ok, err = _staff_required(request)
    if not ok:
        return err

    if request.user.is_superuser:
        companies = Company.objects.prefetch_related("stores", "branding").order_by("name")
    else:
        company_ids = UserRole.objects.filter(user=request.user).values_list("company_id", flat=True).distinct()
        companies = Company.objects.filter(id__in=company_ids).prefetch_related("stores", "branding").order_by("name")

    total_stores = sum(c.stores.count() for c in companies)

    return render(request, "admin_panel/company_list.html", {
        "companies": companies,
        "total_stores": total_stores,
        "active_tab": "empresas",
    })


@login_required
def company_create(request):
    ok, err = _staff_required(request)
    if not ok:
        return err

    company_form = CompanyAdminForm(request.POST or None)
    branding_form = CompanyBrandingAdminForm(request.POST or None)

    if request.method == "POST" and company_form.is_valid() and branding_form.is_valid():
        with transaction.atomic():
            company = company_form.save()
            branding = branding_form.save(commit=False)
            branding.company = company
            branding.save()
        messages.success(request, f"Empresa '{company.name}' creada correctamente.")
        return redirect("users:company_list")

    preset_colors = [
        ("#066fd1", "Skin 1"), ("#1AB394", "Md Skin"), ("#23C6C8", "Skin 2"),
        ("#ECBA52", "Skin 3"), ("#94C748", "Skin 4"),
    ]
    return render(request, "admin_panel/company_form.html", {
        "company_form": company_form,
        "branding_form": branding_form,
        "preset_colors": preset_colors,
        "active_tab": "empresas",
        "title": "Nueva Empresa",
        "submit_label": "Crear empresa",
        "is_new": True,
    })


@login_required
def company_edit(request, pk):
    ok, err = _staff_required(request)
    if not ok:
        return err

    company = get_object_or_404(Company, pk=pk)
    branding, _ = CompanyBranding.objects.get_or_create(company=company)
    stores = company.stores.order_by("name")

    company_form = CompanyAdminForm(request.POST or None, instance=company)
    branding_form = CompanyBrandingAdminForm(request.POST or None, instance=branding)

    if request.method == "POST" and company_form.is_valid() and branding_form.is_valid():
        with transaction.atomic():
            company_form.save()
            branding_form.save()
        messages.success(request, "Empresa actualizada correctamente.")
        return redirect("users:company_edit", pk=company.pk)

    preset_colors = [
        ("#066fd1", "Skin 1"), ("#1AB394", "Md Skin"), ("#23C6C8", "Skin 2"),
        ("#ECBA52", "Skin 3"), ("#94C748", "Skin 4"),
    ]
    return render(request, "admin_panel/company_form.html", {
        "company": company,
        "company_form": company_form,
        "branding_form": branding_form,
        "stores": stores,
        "preset_colors": preset_colors,
        "active_tab": "empresas",
        "title": f"Editar: {company.name}",
        "submit_label": "Guardar cambios",
        "is_new": False,
    })


@login_required
def company_delete(request, pk):
    ok, err = _staff_required(request)
    if not ok:
        return err

    company = get_object_or_404(Company, pk=pk)

    if request.method == "POST":
        name = company.name
        company.delete()
        messages.success(request, f"Empresa '{name}' eliminada.")
        return redirect("users:company_list")

    return render(request, "admin_panel/company_confirm_delete.html", {
        "company": company,
        "active_tab": "empresas",
    })


# ─────────────────────────────────────────────
# Gestión de Tiendas / Sucursales
# ─────────────────────────────────────────────

@login_required
def store_create(request, company_pk):
    ok, err = _staff_required(request)
    if not ok:
        return err

    company = get_object_or_404(Company, pk=company_pk)
    form = StoreAdminForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            store = form.save(commit=False)
            store.company = company
            store.save()

            # Propagar acceso a la nueva sucursal para usuarios que ya tienen
            # acceso a la empresa (global) o roles dentro de la empresa.
            company_access_user_ids = UserCompanyAccess.objects.filter(
                company=company,
                store__isnull=True,
            ).values_list("user_id", flat=True)
            role_user_ids = UserRole.objects.filter(company=company).values_list("user_id", flat=True)

            target_user_ids = set(list(company_access_user_ids) + list(role_user_ids) + [request.user.id])
            for user_id in target_user_ids:
                UserCompanyAccess.objects.get_or_create(
                    user_id=user_id,
                    company=company,
                    store=store,
                    defaults={"is_default": False},
                )
        messages.success(request, f"Sucursal '{store.name}' creada.")
        return redirect("users:company_edit", pk=company.pk)

    return render(request, "admin_panel/store_form.html", {
        "form": form,
        "company": company,
        "active_tab": "empresas",
        "title": f"Nueva sucursal — {company.name}",
        "submit_label": "Crear sucursal",
    })


@login_required
def store_edit(request, company_pk, pk):
    ok, err = _staff_required(request)
    if not ok:
        return err

    company = get_object_or_404(Company, pk=company_pk)
    store = get_object_or_404(Store, pk=pk, company=company)
    form = StoreAdminForm(request.POST or None, instance=store)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Sucursal '{store.name}' actualizada.")
        return redirect("users:company_edit", pk=company.pk)

    return render(request, "admin_panel/store_form.html", {
        "form": form,
        "company": company,
        "store": store,
        "active_tab": "empresas",
        "title": f"Editar sucursal — {store.name}",
        "submit_label": "Guardar cambios",
    })


@login_required
def store_delete(request, company_pk, pk):
    ok, err = _staff_required(request)
    if not ok:
        return err

    company = get_object_or_404(Company, pk=company_pk)
    store = get_object_or_404(Store, pk=pk, company=company)

    if request.method == "POST":
        name = store.name
        store.delete()
        messages.success(request, f"Sucursal '{name}' eliminada.")
        return redirect("users:company_edit", pk=company.pk)

    return render(request, "admin_panel/store_confirm_delete.html", {
        "store": store,
        "company": company,
        "active_tab": "empresas",
    })


# ─────────────────────────────────────────────
# Configuración General
# ─────────────────────────────────────────────

@login_required
def configuracion(request):
    ok, err = _staff_required(request)
    if not ok:
        return err

    from django.urls import NoReverseMatch, reverse
    from apps.inventory.models import Brand, Category, Unit, Warehouse, WarehouseLocation

    company = _get_active_company(request)
    item = request.GET.get("item", None)

    item_label = None
    item_objects = []
    item_add_url = None    # pre-resolved (no pk needed)
    item_edit_url = None   # named URL — used in template with obj.pk
    item_delete_url = None

    if item:
        if item == "almacenes":
            item_label = "Almacenes"
            qs = (Warehouse.objects.filter(store__company=company).select_related("store")
                  if company else Warehouse.objects.none())
            item_objects = list(qs.order_by("store__name", "name"))
            item_add_url = reverse("inventory:warehouse_create")
            item_edit_url = "inventory:warehouse_update"
            item_delete_url = "inventory:warehouse_delete"
        elif item == "ubicaciones":
            item_label = "Ubicaciones en Bodega"
            qs = (WarehouseLocation.objects.filter(warehouse__store__company=company).select_related("warehouse")
                  if company else WarehouseLocation.objects.none())
            item_objects = list(qs.order_by("warehouse__name", "code"))
            item_add_url = reverse("inventory:warehouse_location_create")
            item_edit_url = "inventory:warehouse_location_update"
            item_delete_url = "inventory:warehouse_location_delete"
        elif item == "categorias":
            item_label = "Categorías"
            item_objects = list(Category.objects.all())
            item_add_url = reverse("inventory:category_create")
            item_edit_url = "inventory:category_update"
            item_delete_url = "inventory:category_delete"
        elif item == "marcas":
            item_label = "Marcas"
            item_objects = list(Brand.objects.all())
            item_add_url = reverse("inventory:brand_create")
            item_edit_url = "inventory:brand_update"
            item_delete_url = "inventory:brand_delete"
        elif item == "unidades":
            item_label = "Unidades de Medida"
            item_objects = list(Unit.objects.all())
            item_add_url = reverse("inventory:unit_create")
            item_edit_url = "inventory:unit_update"
            item_delete_url = "inventory:unit_delete"

    return render(request, "admin_panel/configuracion.html", {
        "active_tab": "configuracion",
        "active_company": company,
        "item": item,
        "item_label": item_label,
        "item_objects": item_objects,
        "item_add_url": item_add_url,
        "item_edit_url": item_edit_url,
        "item_delete_url": item_delete_url,
    })
