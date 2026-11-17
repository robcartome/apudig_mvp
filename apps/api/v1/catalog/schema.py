from drf_spectacular.extensions import OpenApiAuthenticationExtension


class CatalogBearerAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.api.v1.catalog.access.CatalogJWTAuthentication"
    name = "CatalogBearerAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
