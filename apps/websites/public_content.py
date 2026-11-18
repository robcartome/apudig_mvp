"""Public projection of one immutable, published editorial revision."""

from copy import deepcopy
from uuid import UUID
from django.db.models import F
from django.utils import timezone
from .documents import normalize_document
from .errors import WebsiteError
from .models import Website, WebsiteDomain, WebsitePageRevision, WebsiteProduct
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
    document["sections"] = [section for section in document["sections"] if section["enabled"]]
    document["banners"] = [item for item in document["banners"] if item["enabled"]]
    document["announcements"]["items"] = [item for item in document["announcements"]["items"] if item["enabled"]] if "announcements" in visible else []
    now = timezone.now().isoformat(timespec="milliseconds").replace("+00:00", "Z")
    document["promotions"] = [item for item in document["promotions"] if item["enabled"] and (not item["startsAt"] or item["startsAt"] <= now) and (not item["endsAt"] or now < item["endsAt"])] if "promotions" in visible else []
    # Editorial selection is immutable; commercial eligibility is live. Never
    # expose references to unpublished/foreign products, nor embed ERP prices.
    referenced_ids = set(document["specials"]["productIds"] if "specials" in visible else [])
    for item in document["promotions"]:
        referenced_ids.update(item["productIds"])
    # Old editorial documents may carry non-UUID demo IDs. Exclude these before
    # the bounded lookup; never scan every publication to resolve a few links.
    valid_ids = set()
    for identifier in referenced_ids:
        try:
            if str(UUID(identifier)) == identifier:
                valid_ids.add(identifier)
        except (ValueError, TypeError, AttributeError):
            continue
    eligible_ids = set(map(str, WebsiteProduct.objects.filter(
        website_id=context.website_id, is_published=True, product__active=True,
        product__company_id=F("website__company_id"),
        product_id__in=valid_ids,
    ).values_list("product_id", flat=True))) if valid_ids else set()
    for item in document["promotions"]:
        item["productIds"] = [identifier for identifier in item["productIds"] if identifier in eligible_ids]
    document["specials"]["productIds"] = [identifier for identifier in document["specials"]["productIds"] if identifier in eligible_ids] if "specials" in visible else []
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
