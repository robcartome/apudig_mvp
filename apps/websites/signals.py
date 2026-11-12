from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Website, WebsiteCatalogSettings, WebsiteMenu, WebsiteMenuItem, WebsitePage, WebsiteSettings


@receiver(post_save, sender=Website)
def ensure_website_settings(sender, instance, created, **kwargs):
    """Every website gets isolated settings without coupling them to ERP branding."""
    if not created:
        return

    defaults = {"business_name": instance.name}
    try:
        branding = instance.company.branding
    except ObjectDoesNotExist:
        branding = None
    if branding:
        defaults.update({
            "logo_url": branding.app_logo_url or branding.pdf_logo_url,
            "primary_color": branding.primary_color or "#0B1F3A",
            "accent_color": branding.secondary_color or "#F97316",
        })
    WebsiteSettings.objects.get_or_create(website=instance, defaults=defaults)
    WebsiteCatalogSettings.objects.get_or_create(website=instance)
    home, _ = WebsitePage.objects.get_or_create(
        website=instance,
        page_type=WebsitePage.PageType.HOME,
        defaults={"slug": "home", "title": "Inicio"},
    )
    header, _ = WebsiteMenu.objects.get_or_create(
        website=instance, location=WebsiteMenu.Location.HEADER,
        defaults={"name": "Navegación principal"},
    )
    WebsiteMenu.objects.get_or_create(
        website=instance, location=WebsiteMenu.Location.FOOTER,
        defaults={"name": "Pie de página"},
    )
    WebsiteMenuItem.objects.get_or_create(
        menu=header, parent=None, position=0,
        defaults={"label": "Inicio", "target_type": WebsiteMenuItem.TargetType.PAGE, "page": home},
    )
