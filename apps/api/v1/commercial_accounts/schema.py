from drf_spectacular.extensions import OpenApiAuthenticationExtension


class CommercialJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.api.v1.commercial_accounts.authentication.CommercialJWTAuthentication"
    name = "CommercialBearer"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT", "description": "Commercial purpose; current account/session authorization required."}


class IdentityAuthenticationScheme(CommercialJWTAuthenticationScheme):
    target_class = "apps.api.v1.commercial_accounts.authentication.CommercialIdentityAuthentication"
    name = "ContextIdentityBearer"
