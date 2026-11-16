"""Public projection of one immutable, published editorial revision."""

from copy import deepcopy
from django.utils import timezone
from .documents import normalize_document
from .errors import WebsiteError
from .models import Website, WebsiteDomain, WebsitePageRevision
from .selectors import resolve_public_website


def published_content(hostname):
    context = resolve_public_website(hostname)
    revision = WebsitePageRevision.objects.get(pk=context.published_revision_id)
    snapshot = revision.snapshot
    if revision.operation != "PUBLISH" or not isinstance(snapshot, dict) or snapshot.get("schemaVersion") != 3 or snapshot.get("templateKey") != "ecommerce":
        raise Website.DoesNotExist
    try:
        document = deepcopy(normalize_document(snapshot.get("document")))
    except WebsiteError as exc:
        raise Website.DoesNotExist from exc
    visible = {section["type"] for section in document["sections"] if section["enabled"]}
    document["sections"] = [section for section in document["sections"] if section["enabled"] and section["type"] not in ("featured", "categories", "specials")]
    document["banners"] = [item for item in document["banners"] if item["enabled"]]
    document["announcements"]["items"] = [item for item in document["announcements"]["items"] if item["enabled"]] if "announcements" in visible else []
    now = timezone.now().isoformat(timespec="milliseconds").replace("+00:00", "Z")
    document["promotions"] = [item for item in document["promotions"] if item["enabled"] and (not item["startsAt"] or item["startsAt"] <= now) and (not item["endsAt"] or now < item["endsAt"])] if "promotions" in visible else []
    for item in document["promotions"]:
        item["productIds"] = []
    document["specials"]["productIds"] = []
    canonical = WebsiteDomain.objects.filter(website_id=context.website_id, is_primary=True, status="ACTIVE", verified_at__isnull=False).values_list("hostname", flat=True).first() or context.hostname
    return {
        "websiteId": str(context.website_id),
        "hostname": context.hostname,
        "canonicalHostname": canonical,
        "templateKey": snapshot["templateKey"],
        "locale": snapshot.get("locale", "es-PE"),
        "currency": snapshot.get("currency", "PEN"),
        "revision": revision.editorial_revision or revision.version,
        "publishedAt": revision.created_at,
        "commerceEnabled": False,
        "content": document,
    }
