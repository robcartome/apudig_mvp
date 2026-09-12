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

from apps.companies.models import (
    Company, CompanyBranding, CompanyOperationalSettings, Store, UserCompanyAccess,
)
from apps.users.forms import (
    CompanyAdminForm,
    CompanyBrandingAdminForm,
    CompanyOperationalSettingsForm,
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
    UserStore,
)
from apps.users.permissions import user_is_company_admin
from apps.users.services import (
    grant_company_admin_access,
    revoke_company_admin_access,
    set_store_access,
)

User = get_user_model()


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _staff_required(request):
    """Authorize APUDIG superusers or an ADMIN role in the active company."""
    if not request.user.is_authenticated:
        return False, redirect("login")
    if not request.user.is_superuser and not user_is_company_admin(
        request.user,
        request.session.get("active_company_id"),
    ):
        return False, HttpResponseForbidden(
            "Acceso restringido a administradores de la empresa activa."
        )
    return True, None


def _get_active_company(request):
    company_id = request.session.get("active_company_id")
    if company_id:
        return Company.objects.filter(pk=company_id).first()
    return None


def _superuser_required(request):
    """Restrict platform-wide configuration to APUDIG personnel."""
    if not request.user.is_authenticated:
        return False, redirect("login")
    if not request.user.is_superuser:
        return False, HttpResponseForbidden(
            "Esta operacion esta reservada al personal de APUDIG."
        )
    return True, None


def _company_users(company):
    role_user_ids = UserRole.objects.filter(company=company).values_list("user_id", flat=True)
    access_user_ids = UserCompanyAccess.objects.filter(company=company).values_list("user_id", flat=True)
    store_user_ids = UserStore.objects.filter(
        store__company=company,
        is_active=True,
    ).values_list("user_id", flat=True)
    return User.objects.filter(
        Q(id__in=role_user_ids)
        | Q(id__in=access_user_ids)
        | Q(id__in=store_user_ids)
    ).distinct()


def _manageable_user_or_404(request, pk, company):
    if request.user.is_superuser:
        return get_object_or_404(User, pk=pk)
    return get_object_or_404(
        _company_users(company).filter(is_superuser=False),
        pk=pk,
    )


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
        qs = _company_users(company).filter(is_superuser=False)

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
        company_count = UserCompanyAccess.objects.for_user(u).values("company").distinct().count()
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
                    store=None,
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

    company = _get_active_company(request)
    target = _manageable_user_or_404(request, pk, company)
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
        available_role_qs = Role.objects.exclude(id__in=assigned_role_ids)
        if not request.user.is_superuser:
            available_role_qs = available_role_qs.exclude(name__iexact="SUPERUSER")
        available_roles = list(available_role_qs)

    # Guardar roles (POST desde tab roles)
    if request.method == "POST" and "save_roles" in request.POST and company:
        selected_ids = request.POST.getlist("role_ids")
        selected_roles = Role.objects.filter(pk__in=selected_ids)
        if not request.user.is_superuser:
            selected_roles = selected_roles.exclude(name__iexact="SUPERUSER")
        selected_roles = list(selected_roles)
        was_company_admin = user_is_company_admin(target, company.pk)
        with transaction.atomic():
            # Eliminar roles no seleccionados
            UserRole.objects.filter(user=target, company=company).exclude(
                role_id__in=[role.pk for role in selected_roles]
            ).delete()
            # Agregar nuevos
            for role in selected_roles:
                UserRole.objects.get_or_create(user=target, role=role, company=company)

            is_company_admin = any(role.name.upper() == "ADMIN" for role in selected_roles)
            if is_company_admin:
                grant_company_admin_access(target, company)
            elif was_company_admin:
                revoke_company_admin_access(target, company)
        messages.success(request, "Roles actualizados correctamente.")
        return redirect(f"{request.path}?tab=roles")

    # ── Tab: Empresas y Sucursales (accesos) ──────────────────────────────
    # Solo superusuarios pueden gestionar los accesos de otros usuarios
    accesos_por_empresa = []
    if request.user.is_superuser or company:
        user_access_pairs = set(
            UserCompanyAccess.objects.for_user(target)
            .values_list("company_id", "store_id")
        )
        store_roles = {
            str(store_id): role
            for store_id, role in UserStore.objects.filter(
                user=target,
                is_active=True,
            ).values_list("store_id", "role")
        }
        # Normalizar: store_id None queda como None, UUID como str
        user_access_set = {
            (str(c), str(s) if s else None)
            for c, s in user_access_pairs
        }
        managed_companies = Company.objects.filter(is_active=True)
        if not request.user.is_superuser:
            managed_companies = managed_companies.filter(pk=company.pk)
        for co in managed_companies.prefetch_related("stores").order_by("name"):
            stores_info = [
                {
                    "store": st,
                    "has_access": (str(co.pk), str(st.pk)) in user_access_set,
                    "role": store_roles.get(str(st.pk), "SELLER"),
                }
                for st in co.stores.filter(active=True).order_by("name")
            ]
            accesos_por_empresa.append({
                "company": co,
                "has_company_access": (str(co.pk), None) in user_access_set,
                "stores": stores_info,
            })

    if request.method == "POST" and "save_accesos" in request.POST and company:
        selected_pairs = request.POST.getlist("access")  # e.g. ["UUID|", "UUID|UUID"]
        desired: set[tuple[str, str | None]] = set()
        for item in selected_pairs:
            parts = item.split("|", 1)
            co_id = parts[0].strip()
            st_id = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
            if co_id:
                desired.add((co_id, st_id))

        allowed_company_ids = {
            str(pk)
            for pk in (
                Company.objects.filter(is_active=True).values_list("pk", flat=True)
                if request.user.is_superuser
                else [company.pk]
            )
        }
        desired = {pair for pair in desired if pair[0] in allowed_company_ids}

        with transaction.atomic():
            # Eliminar los accesos que ya no están seleccionados
            managed_accesses = UserCompanyAccess.objects.for_user(target).filter(
                company_id__in=allowed_company_ids,
            ).select_related("company", "store")
            for access in managed_accesses:
                key = (str(access.company_id), str(access.store_id) if access.store_id else None)
                if key not in desired:
                    access.delete()
                    if access.store_id:
                        UserStore.objects.filter(user=target, store_id=access.store_id).delete()
            # Agregar los accesos nuevos
            for co_id, st_id in desired:
                co = Company.objects.filter(pk=co_id).first()
                if not co:
                    continue
                if st_id:
                    store = Store.objects.filter(pk=st_id, company=co, active=True).first()
                    if not store:
                        continue
                    role = request.POST.get(f"store_role_{st_id}", "SELLER").upper()
                    valid_roles = {choice[0] for choice in UserStore.ROLE_CHOICES}
                    set_store_access(
                        target,
                        store,
                        role if role in valid_roles else "SELLER",
                    )
                else:
                    UserCompanyAccess.objects.get_or_create(
                        user=target,
                        company=co,
                        store=None,
                        defaults={"is_default": False},
                    )
            for co in Company.objects.filter(pk__in=allowed_company_ids):
                if user_is_company_admin(target, co.pk):
                    grant_company_admin_access(target, co)
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

    company = _get_active_company(request)
    target = _manageable_user_or_404(request, pk, company)

    if target == request.user:
        messages.error(request, "No puedes eliminar tu propia cuenta.")
        return redirect("users:user_list")

    if request.method == "POST":
        email = target.email
        if request.user.is_superuser:
            target.delete()
            messages.success(request, f"Usuario '{email}' eliminado.")
        else:
            with transaction.atomic():
                UserRole.objects.filter(user=target, company=company).delete()
                UserCompanyAccess.objects.filter(user=target, company=company).delete()
                UserStore.objects.filter(user=target, store__company=company).delete()
                UserOperationalFlags.objects.filter(user=target, company=company).delete()
            messages.success(
                request,
                f"Acceso de '{email}' retirado de {company.name}.",
            )
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
    ok, err = _superuser_required(request)
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
    ok, err = _superuser_required(request)
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
    ok, err = _superuser_required(request)
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
    ok, err = _superuser_required(request)
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
    ok, err = _superuser_required(request)
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
    ok, err = _superuser_required(request)
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
    ok, err = _superuser_required(request)
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
    ok, err = _superuser_required(request)
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
        companies = Company.objects.filter(
            pk=request.session.get("active_company_id")
        ).prefetch_related("stores", "branding").order_by("name")

    total_stores = sum(c.stores.count() for c in companies)

    return render(request, "admin_panel/company_list.html", {
        "companies": companies,
        "total_stores": total_stores,
        "active_tab": "empresas",
    })


@login_required
def company_create(request):
    ok, err = _superuser_required(request)
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

    companies = Company.objects.all()
    if not request.user.is_superuser:
        companies = companies.filter(pk=request.session.get("active_company_id"))
    company = get_object_or_404(companies, pk=pk)
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
    ok, err = _superuser_required(request)
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

    companies = Company.objects.all()
    if not request.user.is_superuser:
        companies = companies.filter(pk=request.session.get("active_company_id"))
    company = get_object_or_404(companies, pk=company_pk)
    form = StoreAdminForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            store = form.save(commit=False)
            store.company = company
            store.save()

            # Propagar acceso a la nueva sucursal para usuarios que ya tienen
            # acceso a la empresa (global) o roles dentro de la empresa.
            company_admin_ids = UserRole.objects.filter(
                company=company,
                role__name__iexact="ADMIN",
            ).values_list("user_id", flat=True)
            platform_admin_ids = User.objects.filter(
                is_superuser=True,
                is_active=True,
            ).values_list("id", flat=True)
            target_user_ids = set(company_admin_ids) | set(platform_admin_ids)
            for user_id in target_user_ids:
                UserCompanyAccess.objects.get_or_create(
                    user_id=user_id,
                    company=company,
                    store=store,
                    defaults={"is_default": False},
                )
                UserStore.objects.update_or_create(
                    user_id=user_id,
                    store=store,
                    defaults={"role": "ADMIN", "is_active": True},
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

    companies = Company.objects.all()
    if not request.user.is_superuser:
        companies = companies.filter(pk=request.session.get("active_company_id"))
    company = get_object_or_404(companies, pk=company_pk)
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

    companies = Company.objects.all()
    if not request.user.is_superuser:
        companies = companies.filter(pk=request.session.get("active_company_id"))
    company = get_object_or_404(companies, pk=company_pk)
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
    from apps.purchases.models import PurchaseCategory
    from apps.sales.models import PaymentMethod, MeansOfPayment

    company = _get_active_company(request)
    item = request.GET.get("item", None)

    operational_form = None
    if company:
        operational_settings, _ = CompanyOperationalSettings.objects.get_or_create(company=company)
        operational_form = CompanyOperationalSettingsForm(
            request.POST or None, instance=operational_settings, company=company,
        )
        if request.method == "POST" and request.POST.get("settings_form") == "operational" and operational_form.is_valid():
            operational_form.save()
            messages.success(request, "Configuracion operativa actualizada para la empresa.")
            return redirect("users:configuracion")

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
        elif item == "condiciones_pago":
            item_label = "Formas de Pago"
            qs = PaymentMethod.objects.filter(company=company).order_by("name") if company else PaymentMethod.objects.none()
            item_objects = list(qs)
            item_add_url = reverse("sales:payment_method_create")
            item_edit_url = "sales:payment_method_update"
            item_delete_url = "sales:payment_method_delete"
        elif item == "medios_pago":
            item_label = "Medios de Pago"
            qs = MeansOfPayment.objects.filter(company=company).order_by("name") if company else MeansOfPayment.objects.none()
            item_objects = list(qs)
            item_add_url = reverse("sales:means_of_payment_create")
            item_edit_url = "sales:means_of_payment_update"
            item_delete_url = "sales:means_of_payment_delete"
        elif item == "categorias_gasto":
            item_label = "Categorias de gasto"
            qs = PurchaseCategory.objects.filter(company=company).order_by("name") if company else PurchaseCategory.objects.none()
            item_objects = list(qs)
            item_add_url = reverse("purchases:expense_category_create")
            item_edit_url = "purchases:expense_category_update"
            item_delete_url = "purchases:expense_category_delete"

    return render(request, "admin_panel/configuracion.html", {
        "active_tab": "configuracion",
        "active_company": company,
        "item": item,
        "item_label": item_label,
        "item_objects": item_objects,
        "item_add_url": item_add_url,
        "item_edit_url": item_edit_url,
        "item_delete_url": item_delete_url,
        "operational_form": operational_form,
    })
