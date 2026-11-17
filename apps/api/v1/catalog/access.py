"""Mandatory, current tenant authorization for the worker catalog APIs."""
import uuid
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.cache import patch_vary_headers
from rest_framework import exceptions

from apps.api.v1.authentication import JWTAuthentication
from apps.companies.models import Company, Store, UserCompanyAccess
from apps.users.models import RolePermission, UserRole
from apps.users.permissions import user_can_access_context, user_is_company_admin, user_store_role


class CatalogJWTAuthentication(JWTAuthentication):
    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except (UnicodeDecodeError, ValueError, ValidationError) as exc:
            raise exceptions.AuthenticationFailed("Credencial inválida.") from exc


def context_uuid(value, required=False):
    if value in (None, "") and not required:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise exceptions.PermissionDenied("Selecciona una empresa válida.", code="COMPANY_REQUIRED") from exc


@dataclass(frozen=True)
class CatalogAccess:
    company_id: uuid.UUID
    store_id: uuid.UUID | None
    can_view_private: bool


def redact_foreign_relations(data, product, access):
    for field in ("brand", "category"):
        relation = getattr(product, field, None)
        if relation is not None and (access is None or relation.company_id != access.company_id):
            data[field] = None
    return data


def resolve_catalog_access(user, claims, *, require_product_permission=True):
    if not user or not user.is_authenticated or not user.is_active:
        raise exceptions.NotAuthenticated()
    claims = claims if isinstance(claims, dict) else {}
    company_id = context_uuid(claims.get("company_id"), required=True)
    store_id = context_uuid(claims.get("store_id"))
    if not Company.objects.filter(pk=company_id, is_active=True).exists():
        raise exceptions.PermissionDenied("La empresa no está activa.")
    if store_id and not Store.objects.filter(pk=store_id, company_id=company_id, active=True).exists():
        raise exceptions.PermissionDenied("Contexto de sucursal inválido.")
    if not user.is_superuser:
        memberships = UserCompanyAccess.objects.filter(user=user, company_id=company_id)
        memberships = memberships.filter(Q(store__isnull=True) | Q(store_id=store_id)) if store_id else memberships.filter(store__isnull=True)
        if not memberships.exists():
            raise exceptions.PermissionDenied("No tienes acceso vigente a esta empresa.")
    if not user_can_access_context(user, company_id, store_id):
        raise exceptions.PermissionDenied("No tienes acceso vigente a este contexto.")
    company_admin = user.is_superuser or user_is_company_admin(user, company_id)
    store_role = user_store_role(user, company_id, store_id)
    if require_product_permission and not company_admin and store_role != "ADMIN":
        roles = UserRole.objects.filter(user=user, company_id=company_id).values("role_id")
        granted = Q(role_id__in=roles)
        if store_role:
            granted |= Q(role__name__iexact=store_role)
        if not RolePermission.objects.filter(granted, permission__code="read.inventory.products").exists():
            raise exceptions.PermissionDenied("Necesitas permiso para consultar productos.")
    return CatalogAccess(company_id, store_id, company_admin)


class CatalogAccessMixin:
    authentication_classes = [CatalogJWTAuthentication]
    private_catalog = False
    require_product_permission = True

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.catalog_access = resolve_catalog_access(
            request.user, request.auth, require_product_permission=self.require_product_permission,
        )
        if self.private_catalog and not self.catalog_access.can_view_private:
            raise exceptions.PermissionDenied("Los datos privados requieren administración de la empresa.")

    def get_company_id(self):
        return self.catalog_access.company_id

    def get_serializer_context(self):
        context = super().get_serializer_context()
        access = getattr(self, "catalog_access", None)
        context["catalog_access"] = access
        context["include_private_fields"] = bool(access and access.can_view_private)
        return context

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        patch_vary_headers(response, ("Authorization",))
        return response
