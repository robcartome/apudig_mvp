from django.apps import AppConfig


class WebsitesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.websites"

    def ready(self):
        # Documentation and fail-closed commercial cleanup; never bootstrap or publish.
        from apps.api.v1.websites import schema  # noqa: F401
        from apps.api.v1.commercial_accounts import schema as commercial_schema  # noqa: F401
        from apps.websites.catalog import signals  # noqa: F401
