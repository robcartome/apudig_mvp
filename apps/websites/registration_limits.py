"""Database-serialized limits shared across workers; trusted proxies opt in."""
from datetime import timedelta
from ipaddress import ip_address, ip_network

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .errors import WebsiteError
from .models import WebsiteRegistrationQuota


def client_address(meta):
    peer = meta.get("REMOTE_ADDR", "")
    try:
        networks = [ip_network(value) for value in settings.WEBSITE_TRUSTED_PROXY_CIDRS]
        trusted = lambda value: any(ip_address(value) in network for network in networks)
        if not trusted(peer):
            return str(ip_address(peer))
        chain = [value.strip() for value in meta.get("HTTP_X_FORWARDED_FOR", "").split(",") if value.strip()]
        if len(chain) > 20:
            return str(ip_address(peer))
        for address in reversed(chain):
            ip_address(address)
            if not trusted(address):
                return str(ip_address(address))
    except ValueError:
        return peer
    return peer


def limits_ready():
    return WebsiteRegistrationQuota._meta.db_table in connection.introspection.table_names()


@transaction.atomic
def consume_budget(hostname, email, origin, *, proof=False):
    if not limits_ready():
        raise WebsiteError("La protección de registro aún no está disponible.", code="REGISTRATION_UNAVAILABLE", status=503)
    now = timezone.now()
    window = now.replace(minute=0, second=0, microsecond=0)
    if proof:
        budgets = [("proof:" + origin, settings.WEBSITE_REGISTRATION_IP_LIMIT * 2)]
    else:
        budgets = [("domain:" + hostname, settings.WEBSITE_REGISTRATION_DOMAIN_LIMIT), ("email:" + email.lower(), settings.WEBSITE_REGISTRATION_EMAIL_LIMIT), ("ip:" + origin, settings.WEBSITE_REGISTRATION_IP_LIMIT), ("total", settings.WEBSITE_REGISTRATION_GLOBAL_LIMIT)]
    for identity, maximum in sorted(budgets):
        key = salted_hmac("website-registration-quota", identity).hexdigest()
        row, _ = WebsiteRegistrationQuota.objects.get_or_create(key=key, window=window)
        row = WebsiteRegistrationQuota.objects.select_for_update().get(pk=row.pk)
        if row.count >= maximum:
            raise WebsiteError("Se alcanzó el límite temporal. Intenta más tarde.", code="REGISTRATION_RATE_LIMIT", status=429)
        row.count += 1
        row.save(update_fields=["count"])
    WebsiteRegistrationQuota.objects.filter(window__lt=window - timedelta(days=1)).delete()
