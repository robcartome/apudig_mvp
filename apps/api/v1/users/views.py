from drf_spectacular.utils import OpenApiExample, extend_schema
from django.contrib.auth import authenticate, get_user_model
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.auth.tokens import build_access_from_refresh_payload, decode_token
from apps.api.v1.users.helpers import get_default_access, make_token_pair

from .serializers import (
    TokenObtainRequestSerializer,
    TokenObtainResponseSerializer,
    TokenRefreshRequestSerializer,
    TokenRefreshResponseSerializer,
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
        tokens = make_token_pair(user, access_obj)

        data = {
            "access": tokens["access"],
            "refresh": tokens["refresh"],
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.display_name,
            },
            "company": (
                {
                    "id": str(access_obj.company_id),
                    "name": access_obj.company.name,
                    "store_id": str(access_obj.store_id) if access_obj.store_id else None,
                    "store_name": access_obj.store.name if access_obj.store else None,
                }
                if access_obj
                else None
            ),
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
        return Response({"access": access}, status=status.HTTP_200_OK)
