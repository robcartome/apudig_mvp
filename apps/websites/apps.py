from django.apps import AppConfig


class WebsitesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.websites"

    def ready(self):
        # Register API documentation only; no bootstrap/publication signals.
        from apps.api.v1.websites import schema  # noqa: F401
