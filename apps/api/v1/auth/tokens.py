import datetime

import jwt
from django.conf import settings

_ALGORITHM = "HS256"


def build_token(payload: dict, ttl: datetime.timedelta) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {**payload, "iat": now, "exp": now + ttl}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def build_access_from_refresh_payload(payload: dict) -> str:
    access_payload = {
        "sub": payload["sub"],
        "email": payload["email"],
        "company_id": payload.get("company_id"),
        "store_id": payload.get("store_id"),
        "type": "access",
    }
    return build_token(access_payload, settings.JWT_ACCESS_TTL)
