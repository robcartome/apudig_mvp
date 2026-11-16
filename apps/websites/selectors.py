"""Fail-closed tenant lookup. Public resolution returns metadata, never a draft."""

import uuid
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db.models import F

from .models import Website, normalize_hostname
from .permissions import require_website_permission


def get_company_website(*, user, company_id, store_id=None, website_id=None, permission="view"):
    context = require_website_permission(user, company_id, permission, store_id)
    queryset = Website.objects.filter(company_id=context.company_id)
    if website_id is not None:
        try:
            website_id = uuid.UUID(str(website_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise Website.DoesNotExist from exc
        queryset = queryset.filter(pk=website_id)
    return queryset.get()


@dataclass(frozen=True)
class PublicWebsiteContext:
    website_id: uuid.UUID
    hostname: str
    template_key: str
    published_revision_id: uuid.UUID


def resolve_public_website(hostname):
    """Resolve an explicit registered host, not request/forwarded headers.

    B1 has no publication service. Even an explicitly PUBLISHED Website fails
    closed until a same-site published Home revision is configured.
    No snapshot, Company data, settings or draft is returned here.
    """
    try:
        hostname = normalize_hostname(hostname)
    except ValidationError as exc:
        raise Website.DoesNotExist from exc
    website = Website.objects.filter(
        company__is_active=True,
        status=Website.Status.PUBLISHED,
        published_at__isnull=False,
        published_revision__isnull=False,
        published_revision__page__website_id=F("pk"),
        published_revision__page__page_type="HOME",
        published_revision__page__status="PUBLISHED",
        published_revision__page__published_version=F("published_revision__version"),
        published_revision__version__gt=0,
        domains__hostname=hostname,
        domains__status="ACTIVE",
        domains__verified_at__isnull=False,
    ).values("id", "template_key", "published_revision_id").get()
    return PublicWebsiteContext(
        website_id=website["id"],
        hostname=hostname,
        template_key=website["template_key"],
        published_revision_id=website["published_revision_id"],
    )
