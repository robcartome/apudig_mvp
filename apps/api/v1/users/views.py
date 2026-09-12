from drf_spectacular.utils import OpenApiExample, extend_schema
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.auth.tokens import build_access_from_refresh_payload, decode_token
from apps.companies.models import Company, UserCompanyAccess
from apps.api.v1.users.helpers import get_company_security_map, get_default_access, make_token_pair
from apps.users.models import Permission, Role, UserRole, UserStore
from apps.users.permissions import user_is_company_admin
from apps.users.services import grant_company_admin_access, revoke_company_admin_access

from .serializers import (
    AssignRoleRequestSerializer,
    CreatePermissionRequestSerializer,
    CreateRoleRequestSerializer,
    LogoutRequestSerializer,
    MyCompaniesResponseSerializer,
    RegisterUserRequestSerializer,
    SelectCompanyRequestSerializer,
    SelectCompanyResponseSerializer,
    TokenObtainRequestSerializer,
    TokenObtainResponseSerializer,
    TokenRefreshRequestSerializer,
    TokenRefreshResponseSerializer,
)


def _serialize_company(access_obj: UserCompanyAccess | None):
    if not access_obj:
        return None
    security = get_company_security_map(access_obj.user).get(str(access_obj.company_id), {"roles": [], "permissions": []})
    return {
        "id": str(access_obj.company_id),
        "name": access_obj.company.name,
        "store_id": str(access_obj.store_id) if access_obj.store_id else None,
        "store_name": access_obj.store.name if access_obj.store else None,
        "roles": security["roles"],
        "permissions": security["permissions"],
    }


def _serialize_company_list(accesses, security_map: dict):
    grouped = {}
    for access in accesses:
        company_id = str(access.company_id)
        if company_id not in grouped:
            grouped[company_id] = {
                "company_id": company_id,
                "company_name": access.company.name,
                "store_id": str(access.store_id) if access.store_id else None,
                "store_name": access.store.name if access.store else None,
                "roles": security_map.get(company_id, {}).get("roles", []),
                "permissions": security_map.get(company_id, {}).get("permissions", []),
            }
        else:
            if not grouped[company_id]["store_id"] and access.store_id:
                grouped[company_id]["store_id"] = str(access.store_id)
                grouped[company_id]["store_name"] = access.store.name if access.store else None
    return list(grouped.values())


def _get_user_companies(user):
    return UserCompanyAccess.objects.filter(user=user).select_related("company", "store")


def _request_company_id(request):
    if isinstance(request.auth, dict) and request.auth.get("company_id"):
        return str(request.auth["company_id"])
    return (
        getattr(request, "active_company_id", None)
        or request.session.get("active_company_id")
    )


def _can_administer_company(request, company_id=None):
    company_id = str(company_id or _request_company_id(request) or "")
    return request.user.is_superuser or user_is_company_admin(request.user, company_id)


def _company_users(company_id):
    role_users = UserRole.objects.filter(company_id=company_id).values_list("user_id", flat=True)
    access_users = UserCompanyAccess.objects.filter(company_id=company_id).values_list("user_id", flat=True)
    store_users = UserStore.objects.filter(
        store__company_id=company_id,
        is_active=True,
    ).values_list("user_id", flat=True)
    User = get_user_model()
    return User.objects.filter(
        Q(pk__in=role_users) | Q(pk__in=access_users) | Q(pk__in=store_users)
    ).distinct()


def _forbidden():
    return Response(
        {"detail": "Se requiere el rol ADMIN en la empresa activa."},
        status=status.HTTP_403_FORBIDDEN,
    )


class TokenObtainAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="Obtain JWT token pair",
        request=TokenObtainRequestSerializer,
        responses={200: TokenObtainResponseSerializer},
        examples=[
            OpenApiExample(
                "TokenResponse",
                value={
                    "access": "eyJ...",
                    "refresh": "eyJ...",
                    "user": {"id": "7d5d4d5a-7e73-4a39-b4a6-3bca21171ccd", "email": "user@erp.pe", "name": "Administrador"},
                    "company": {
                        "id": "5c4b6f66-0f08-4f75-a0ba-063d737dae12",
                        "name": "Ferreteria Demo",
                        "store_id": "59ed13f0-a503-4ca4-a22b-c2e0d8c2a77e",
                        "store_name": "Tienda Principal",
                    },
                },
                response_only=True,
            )
        ],
    )
    def post(self, request):
        serializer = TokenObtainRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip()
        normalized_email = email.lower()
        password = serializer.validated_data["password"]

        user = authenticate(request, username=normalized_email, password=password)
        if user is None:
            user = authenticate(request, email=normalized_email, password=password)
        if user is None:
            User = get_user_model()
            candidate = User.objects.filter(email__iexact=normalized_email, is_active=True).first()
            if candidate and candidate.check_password(password):
                user = candidate

        if user is None:
            raise serializers.ValidationError({"detail": "Credenciales incorrectas."})
        if not user.is_active:
            return Response({"detail": "Cuenta desactivada."}, status=status.HTTP_403_FORBIDDEN)

        access_obj = get_default_access(user)
        user_companies = _get_user_companies(user)
        security_map = get_company_security_map(user)
        tokens = make_token_pair(user, access_obj)

        data = {
            "access": tokens["access"],
            "refresh": tokens["refresh"],
            "access_token": tokens["access"],
            "refresh_token": tokens["refresh"],
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.display_name,
            },
            "company": _serialize_company(access_obj),
            "companies": _serialize_company_list(user_companies, security_map),
        }
        return Response(data, status=status.HTTP_200_OK)


class TokenRefreshAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="Refresh access token",
        request=TokenRefreshRequestSerializer,
        responses={200: TokenRefreshResponseSerializer},
    )
    def post(self, request):
        serializer = TokenRefreshRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payload = decode_token(serializer.validated_data["refresh"])
        if payload is None or payload.get("type") != "refresh":
            return Response({"detail": "Token invalido o expirado."}, status=status.HTTP_401_UNAUTHORIZED)

        access = build_access_from_refresh_payload(payload)
        return Response({"access": access, "access_token": access}, status=status.HTTP_200_OK)


class AuthMeAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Auth"], summary="Get authenticated user profile")
    def get(self, request):
        user = request.user
        auth_payload = request.auth if isinstance(request.auth, dict) else {}
        company_id = auth_payload.get("company_id")
        store_id = auth_payload.get("store_id")

        access_obj = None
        if company_id:
            access_obj = (
                UserCompanyAccess.objects.filter(user=user, company_id=company_id)
                .select_related("company", "store")
                .first()
            )
            if access_obj and store_id and str(access_obj.store_id or "") != str(store_id):
                access_obj = (
                    UserCompanyAccess.objects.filter(user=user, company_id=company_id, store_id=store_id)
                    .select_related("company", "store")
                    .first()
                )
        if not access_obj:
            access_obj = get_default_access(user)

        data = {
            "id": str(user.id),
            "email": user.email,
            "name": user.display_name,
            "company": _serialize_company(access_obj),
        }
        return Response(data, status=status.HTTP_200_OK)


class MyCompaniesAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Auth"], summary="List accessible companies", responses={200: MyCompaniesResponseSerializer})
    def get(self, request):
        user_companies = _get_user_companies(request.user)
        security_map = get_company_security_map(request.user)
        payload = _serialize_company_list(user_companies, security_map)
        return Response(payload, status=status.HTTP_200_OK)


class SelectCompanyAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Auth"],
        summary="Select active company and issue scoped token",
        request=SelectCompanyRequestSerializer,
        responses={200: SelectCompanyResponseSerializer},
    )
    def post(self, request):
        serializer = SelectCompanyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        company_id = serializer.validated_data["company_id"]
        access_obj = (
            UserCompanyAccess.objects.filter(user=request.user, company_id=company_id)
            .select_related("company", "store")
            .first()
        )
        if not access_obj:
            return Response({"detail": "No tienes acceso a la empresa seleccionada."}, status=status.HTTP_403_FORBIDDEN)

        tokens = make_token_pair(request.user, access_obj)
        return Response(
            {
                "access": tokens["access"],
                "access_token": tokens["access"],
            },
            status=status.HTTP_200_OK,
        )


class LogoutAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["Auth"], summary="Logout (stateless noop)", request=LogoutRequestSerializer)
    def post(self, _request):
        return Response(status=status.HTTP_204_NO_CONTENT)


class UsersListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Auth"], summary="List users")
    def get(self, request):
        company_id = _request_company_id(request)
        if not _can_administer_company(request, company_id):
            return _forbidden()
        User = get_user_model()
        users = (
            User.objects.filter(is_active=True).order_by("email")
            if request.user.is_superuser
            else _company_users(company_id).filter(is_active=True, is_superuser=False).order_by("email")
        )
        payload = [
            {
                "id": str(user.id),
                "email": user.email,
                "name": user.display_name,
                "phone": user.phone,
            }
            for user in users
        ]
        return Response(payload, status=status.HTTP_200_OK)


class RegisterUserAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Auth"], summary="Register user", request=RegisterUserRequestSerializer)
    def post(self, request):
        company_id = _request_company_id(request)
        if not company_id or not _can_administer_company(request, company_id):
            return _forbidden()
        company = Company.objects.filter(pk=company_id, is_active=True).first()
        if not company:
            return Response(
                {"detail": "La empresa activa no existe o esta inactiva."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = RegisterUserRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        User = get_user_model()
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=serializer.validated_data["email"].lower().strip(),
                    password=serializer.validated_data["password"],
                    name=serializer.validated_data.get("name", ""),
                    phone=serializer.validated_data.get("phone", ""),
                )
                UserCompanyAccess.objects.create(
                    user=user,
                    company=company,
                    store=None,
                    is_default=True,
                )
        except IntegrityError:
            return Response({"detail": "Ya existe un usuario con ese email."}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "id": str(user.id),
                "email": user.email,
                "name": user.display_name,
                "phone": user.phone,
            },
            status=status.HTTP_201_CREATED,
        )


class RolesAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Auth"], summary="List roles")
    def get(self, request):
        if not _can_administer_company(request):
            return _forbidden()
        roles = Role.objects.all()
        if not request.user.is_superuser:
            roles = roles.exclude(name__iexact="SUPERUSER")
        roles = roles.order_by("name")
        payload = [{"id": str(role.id), "name": role.name, "description": role.description} for role in roles]
        return Response(payload, status=status.HTTP_200_OK)

    @extend_schema(tags=["Auth"], summary="Create role", request=CreateRoleRequestSerializer)
    def post(self, request):
        if not request.user.is_superuser:
            return _forbidden()
        serializer = CreateRoleRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            role = Role.objects.create(
                name=serializer.validated_data["name"].strip(),
                description=serializer.validated_data.get("description", "").strip(),
            )
        except IntegrityError:
            return Response({"detail": "El rol ya existe."}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"id": str(role.id), "name": role.name, "description": role.description},
            status=status.HTTP_201_CREATED,
        )


class PermissionsAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Auth"], summary="List permissions")
    def get(self, request):
        if not _can_administer_company(request):
            return _forbidden()
        permissions_qs = Permission.objects.all().order_by("code")
        payload = [
            {
                "id": str(permission.id),
                "code": permission.code,
                "description": permission.description,
            }
            for permission in permissions_qs
        ]
        return Response(payload, status=status.HTTP_200_OK)

    @extend_schema(tags=["Auth"], summary="Create permission", request=CreatePermissionRequestSerializer)
    def post(self, request):
        if not request.user.is_superuser:
            return _forbidden()
        serializer = CreatePermissionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            permission = Permission.objects.create(
                code=serializer.validated_data["code"].strip(),
                description=serializer.validated_data.get("description", "").strip(),
            )
        except IntegrityError:
            return Response({"detail": "El permiso ya existe."}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "id": str(permission.id),
                "code": permission.code,
                "description": permission.description,
            },
            status=status.HTTP_201_CREATED,
        )


class AssignRoleAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Auth"], summary="Assign role to user in company", request=AssignRoleRequestSerializer)
    def post(self, request):
        serializer = AssignRoleRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        company_id = serializer.validated_data["company_id"]
        if not _can_administer_company(request, company_id):
            return _forbidden()

        User = get_user_model()
        try:
            users = User.objects.all() if request.user.is_superuser else _company_users(company_id).filter(is_superuser=False)
            user = users.get(pk=serializer.validated_data["user_id"])
            role = Role.objects.get(pk=serializer.validated_data["role_id"])
        except (User.DoesNotExist, Role.DoesNotExist):
            return Response({"detail": "Usuario o rol no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        if role.name.upper() == "SUPERUSER" and not request.user.is_superuser:
            return _forbidden()

        role_assignment, _ = UserRole.objects.get_or_create(
            user=user,
            role=role,
            company_id=company_id,
        )
        if role.name.upper() == "ADMIN":
            grant_company_admin_access(user, role_assignment.company)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RemoveRoleAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Auth"], summary="Remove role from user in company", request=AssignRoleRequestSerializer)
    def post(self, request):
        serializer = AssignRoleRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        company_id = serializer.validated_data["company_id"]
        if not _can_administer_company(request, company_id):
            return _forbidden()

        assignment = UserRole.objects.filter(
            user_id=serializer.validated_data["user_id"],
            role_id=serializer.validated_data["role_id"],
            company_id=company_id,
        ).select_related("role", "company").first()
        if not assignment:
            return Response({"detail": "Asignacion no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        was_admin = assignment.role.name.upper() == "ADMIN"
        company = assignment.company
        assigned_user = assignment.user
        assignment.delete()
        if was_admin:
            revoke_company_admin_access(assigned_user, company)
        return Response(status=status.HTTP_204_NO_CONTENT)
