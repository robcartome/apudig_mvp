from drf_spectacular.extensions import OpenApiAuthenticationExtension


class WebsiteBearerAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.api.v1.websites.views.WebsiteJWTAuthentication"
    name = "BearerAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
