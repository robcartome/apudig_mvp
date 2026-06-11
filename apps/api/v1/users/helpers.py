from apps.api.v1.auth.tokens import build_token
from apps.companies.models import UserCompanyAccess
from apps.users.models import UserRole
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


def get_company_security_map(user) -> dict:
    user_roles = (
        UserRole.objects.filter(user=user)
        .select_related("role", "company")
        .prefetch_related("role__role_permissions__permission")
    )

    security_map = {}
    for user_role in user_roles:
        company_id = str(user_role.company_id)
        current = security_map.setdefault(company_id, {"roles": set(), "permissions": set()})
        current["roles"].add(user_role.role.name)
        for role_permission in user_role.role.role_permissions.all():
            permission_code = getattr(role_permission.permission, "code", None)
            if permission_code:
                current["permissions"].add(permission_code)

    return {
        company_id: {
            "roles": sorted(list(data["roles"])),
            "permissions": sorted(list(data["permissions"])),
        }
        for company_id, data in security_map.items()
    }


def make_token_pair(user, access_obj: UserCompanyAccess | None) -> dict:
    security = {"roles": [], "permissions": []}
    if access_obj:
        security = get_company_security_map(user).get(str(access_obj.company_id), security)

    base_payload = {
        "sub": str(user.id),
        "email": user.email,
        "company_id": str(access_obj.company_id) if access_obj else None,
        "store_id": str(access_obj.store_id) if access_obj and access_obj.store_id else None,
        "roles": security["roles"],
        "permissions": security["permissions"],
    }
    access_token = build_token({**base_payload, "type": "access"}, settings.JWT_ACCESS_TTL)
    refresh_token = build_token({**base_payload, "type": "refresh"}, settings.JWT_REFRESH_TTL)
    return {"access_token": access_token, "refresh_token": refresh_token, "access": access_token, "refresh": refresh_token}
