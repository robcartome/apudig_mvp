from rest_framework import exceptions
from django.core.exceptions import ValidationError

from apps.api.v1.authentication import JWTAuthentication
from apps.websites.commercial_sessions import resolve_session
from apps.websites.errors import WebsiteError


class CommercialIdentityAuthentication(JWTAuthentication):
    """An existing identity may explicitly enter another authorized context."""
    allowed_purposes = (None, "erp", "commercial")

    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        try:
            result = super().authenticate(request)
            if result and result[1].get("purpose") == "commercial":
                resolve_session(result[1], result[1].get("hostname"))
            return result
        except (UnicodeDecodeError, ValueError, ValidationError) as exc:
            raise exceptions.AuthenticationFailed("Credencial inválida.") from exc
        except WebsiteError as exc:
            raise exceptions.AuthenticationFailed(str(exc)) from exc


class CommercialJWTAuthentication(CommercialIdentityAuthentication):
    allowed_purposes = ("commercial",)
