from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


class StorefrontQuoteThrottle(SimpleRateThrottle):
    scope = "storefront_quote"

    def get_rate(self):
        return getattr(settings, "STOREFRONT_QUOTE_RATE", "20/min")

    def get_cache_key(self, request, view):
        hostname = str(view.kwargs.get("hostname", "unknown"))[:253].lower()
        ident = self.get_ident(request)
        return self.cache_format % {
            "scope": self.scope,
            "ident": f"{hostname}:{ident}",
        }
