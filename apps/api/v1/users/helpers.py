from apps.api.v1.auth.tokens import build_token
from apps.companies.models import UserCompanyAccess
from django.conf import settings


def get_default_access(user) -> UserCompanyAccess | None:
    return (
        UserCompanyAccess.objects.filter(user=user, is_default=True)
        .select_related("company", "store")
        .first()
        or UserCompanyAccess.objects.filter(user=user)
        .select_related("company", "store")
        .first()
    )


def make_token_pair(user, access_obj: UserCompanyAccess | None) -> dict:
    base_payload = {
        "sub": str(user.id),
        "email": user.email,
        "company_id": str(access_obj.company_id) if access_obj else None,
        "store_id": str(access_obj.store_id) if access_obj and access_obj.store_id else None,
    }
    access_token = build_token({**base_payload, "type": "access"}, settings.JWT_ACCESS_TTL)
    refresh_token = build_token({**base_payload, "type": "refresh"}, settings.JWT_REFRESH_TTL)
    return {"access_token": access_token, "refresh_token": refresh_token, "access": access_token, "refresh": refresh_token}
