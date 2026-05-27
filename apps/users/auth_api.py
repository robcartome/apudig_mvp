"""
users/auth_api.py — JWT token endpoints for frontend (Next.js) integration.

POST /api/auth/token/     → obtain access + refresh tokens
POST /api/auth/token/refresh/  → renew access token with a valid refresh token
"""
import json
import datetime

import jwt
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.companies.models import UserCompanyAccess

User = get_user_model()

_ALGORITHM = "HS256"


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_token(payload: dict, ttl: datetime.timedelta) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {**payload, "iat": now, "exp": now + ttl}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=_ALGORITHM)


def _decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def _default_access(user) -> UserCompanyAccess | None:
    return (
        UserCompanyAccess.objects.filter(user=user, is_default=True)
        .select_related("company", "store")
        .first()
        or UserCompanyAccess.objects.filter(user=user)
        .select_related("company", "store")
        .first()
    )


def _make_token_pair(user, access_obj: UserCompanyAccess | None) -> dict:
    base_payload = {
        "sub": str(user.id),
        "email": user.email,
        "company_id": str(access_obj.company_id) if access_obj else None,
        "store_id": str(access_obj.store_id) if access_obj and access_obj.store_id else None,
    }
    access_token = _build_token({**base_payload, "type": "access"}, settings.JWT_ACCESS_TTL)
    refresh_token = _build_token({**base_payload, "type": "refresh"}, settings.JWT_REFRESH_TTL)
    return {"access_token": access_token, "refresh_token": refresh_token}


# ─────────────────────────────────────────────────────────────────────────────
# Public helpers used by catalog_api
# ─────────────────────────────────────────────────────────────────────────────

def decode_bearer(request) -> dict | None:
    """Extract and validate Bearer token from Authorization header.
    Returns decoded payload dict or None."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[len("Bearer "):]
    payload = _decode_token(token)
    if payload and payload.get("type") == "access":
        return payload
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def obtain_token(request):
    """
    POST /api/auth/token/
    Body: { "email": "...", "password": "..." }
    Returns: { access_token, refresh_token, user, company }
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"detail": "Cuerpo JSON inválido."}, status=400)

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return JsonResponse({"detail": "email y password son requeridos."}, status=400)

    user = authenticate(request, username=email, password=password)
    if user is None:
        return JsonResponse({"detail": "Credenciales incorrectas."}, status=401)

    if not user.is_active:
        return JsonResponse({"detail": "Cuenta desactivada."}, status=403)

    access_obj = _default_access(user)
    tokens = _make_token_pair(user, access_obj)

    return JsonResponse(
        {
            **tokens,
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
        },
        status=200,
    )


@csrf_exempt
@require_POST
def refresh_token(request):
    """
    POST /api/auth/token/refresh/
    Body: { "refresh_token": "..." }
    Returns: { access_token }
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"detail": "Cuerpo JSON inválido."}, status=400)

    raw = (data.get("refresh_token") or "").strip()
    if not raw:
        return JsonResponse({"detail": "refresh_token es requerido."}, status=400)

    payload = _decode_token(raw)
    if payload is None or payload.get("type") != "refresh":
        return JsonResponse({"detail": "Token inválido o expirado."}, status=401)

    # Re-issue access token with same claims
    access_payload = {
        "sub": payload["sub"],
        "email": payload["email"],
        "company_id": payload.get("company_id"),
        "store_id": payload.get("store_id"),
        "type": "access",
    }
    new_access = _build_token(access_payload, settings.JWT_ACCESS_TTL)
    return JsonResponse({"access_token": new_access}, status=200)
