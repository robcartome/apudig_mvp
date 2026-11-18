"""Deleting an override list must never silently select the default list."""
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone

from apps.core.models import AuditLog
from apps.inventory.models import PriceList
from apps.websites.models import Website, WebsiteProduct


@receiver(pre_delete, sender=PriceList, dispatch_uid="website_withdraw_deleted_price_override")
def withdraw_deleted_price_override(sender, instance, using, **kwargs):
    publications = WebsiteProduct.objects.using(using).filter(price_list_id=instance.pk, is_published=True)
    website_ids = publications.values_list("website_id", flat=True).distinct()
    for website in Website.objects.using(using).select_for_update().filter(pk__in=website_ids).order_by("pk"):
        rows = publications.filter(website=website)
        ids = list(map(str, rows.values_list("pk", flat=True)))
        rows.update(is_published=False, updated_at=timezone.now())
        AuditLog.objects.using(using).create(
            action="WEBSITE_PRODUCTS_WITHDRAW_OVERRIDE_DELETED", entity="WebsiteCatalog", entity_id=str(website.pk),
            meta_data={"priceListId": str(instance.pk), "publicationIds": ids, "reason": "ERP price-list deletion; no default-price fallback"},
        )
