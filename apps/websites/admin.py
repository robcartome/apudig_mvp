from django.contrib import admin

from .models import Website, WebsiteCatalogSettings, WebsiteDomain, WebsiteMedia, WebsiteMenu, WebsiteMenuItem, WebsitePage, WebsitePageRevision, WebsiteProduct, WebsiteSection, WebsiteSettings


class WebsiteDomainInline(admin.TabularInline):
    model = WebsiteDomain
    extra = 0


class WebsiteSettingsInline(admin.StackedInline):
    model = WebsiteSettings
    extra = 0
    max_num = 1


class WebsiteCatalogSettingsInline(admin.StackedInline):
    model = WebsiteCatalogSettings
    extra = 0
    max_num = 1


class WebsiteSectionInline(admin.StackedInline):
    model = WebsiteSection
    extra = 0


@admin.register(Website)
class WebsiteAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "slug", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("name", "company__name", "company__ruc")
    inlines = (WebsiteDomainInline, WebsiteSettingsInline, WebsiteCatalogSettingsInline)


@admin.register(WebsiteDomain)
class WebsiteDomainAdmin(admin.ModelAdmin):
    list_display = ("hostname", "website", "kind", "status", "is_primary", "verified_at")
    list_filter = ("kind", "status", "is_primary")
    search_fields = ("hostname", "website__name", "website__company__name")


@admin.register(WebsiteSettings)
class WebsiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("website", "business_name", "updated_at")
    search_fields = ("website__name", "business_name", "website__company__name")


@admin.register(WebsitePage)
class WebsitePageAdmin(admin.ModelAdmin):
    list_display = ("title", "website", "page_type", "status", "draft_version", "published_version")
    list_filter = ("page_type", "status")
    search_fields = ("title", "slug", "website__name", "website__company__name")
    inlines = (WebsiteSectionInline,)


@admin.register(WebsitePageRevision)
class WebsitePageRevisionAdmin(admin.ModelAdmin):
    list_display = ("page", "version", "created_by", "created_at")
    readonly_fields = ("page", "version", "snapshot", "created_by", "created_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class WebsiteMenuItemInline(admin.TabularInline):
    model = WebsiteMenuItem
    extra = 0


@admin.register(WebsiteMenu)
class WebsiteMenuAdmin(admin.ModelAdmin):
    list_display = ("name", "website", "location", "status", "draft_version", "published_version")
    list_filter = ("location", "status")
    inlines = (WebsiteMenuItemInline,)


@admin.register(WebsiteMedia)
class WebsiteMediaAdmin(admin.ModelAdmin):
    list_display = ("original_name", "website", "kind", "width", "height", "is_deleted", "created_at")
    list_filter = ("kind", "is_deleted")
    search_fields = ("original_name", "alt_text", "website__name")


@admin.register(WebsiteProduct)
class WebsiteProductAdmin(admin.ModelAdmin):
    list_display = ("product", "website", "slug", "is_published", "is_featured", "position")
    list_filter = ("is_published", "is_featured")
    search_fields = ("product__name", "product__sku", "slug", "website__name")
