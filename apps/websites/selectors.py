from django.db.models import DecimalField, OuterRef, Q, Subquery, Sum, UUIDField, Value
from django.db.models.functions import Coalesce

from apps.inventory.models import ProductPrice, StockByWarehouse

from .models import (
    Website,
    WebsiteCatalogSettings,
    WebsiteDomain,
    WebsitePage,
    WebsitePageRevision,
    WebsiteProduct,
    normalize_hostname,
)


def get_public_website_by_hostname(hostname: str):
    """Resolve only an active, verified domain belonging to a published site."""
    normalized = normalize_hostname(hostname)
    return (
        Website.objects.select_related("company", "settings").prefetch_related("domains")
        .filter(
            status=Website.Status.PUBLISHED,
            company__is_active=True,
            domains__hostname=normalized,
            domains__status=WebsiteDomain.Status.ACTIVE,
            domains__verified_at__isnull=False,
        )
        .distinct()
        .get()
    )


def get_company_website(company_id):
    """Return the single website owned by an explicit company scope."""
    if not company_id:
        raise Website.DoesNotExist
    return Website.objects.select_related("company", "settings").get(
        company_id=company_id,
    )


def get_published_page_by_hostname(hostname, slug):
    website = get_public_website_by_hostname(hostname)
    page = WebsitePage.objects.get(
        website=website, slug=slug, status=WebsitePage.Status.PUBLISHED,
        published_version__gt=0,
    )
    revision = WebsitePageRevision.objects.get(page=page, version=page.published_version)
    return website, page, revision


def get_catalog_settings(website):
    settings_object, _ = WebsiteCatalogSettings.objects.get_or_create(website=website)
    return settings_object


def get_public_website_products(website, *, include_hidden_out_of_stock=False):
    """Published links annotated with one public price and aggregate availability."""
    catalog_settings = get_catalog_settings(website)
    warehouse_ids = list(
        catalog_settings.warehouses.filter(active=True).values_list("pk", flat=True)
    )

    queryset = (
        WebsiteProduct.objects.filter(
            website=website,
            is_published=True,
            product__active=True,
            product__company_id=website.company_id,
        )
        .select_related(
            "product__unit", "product__brand", "product__category", "price_list"
        )
        .annotate(
            effective_price_list_id=Coalesce(
                "price_list_id",
                Value(catalog_settings.default_price_list_id),
                output_field=UUIDField(),
            )
        )
    )

    price_subquery = (
        ProductPrice.objects.filter(
            product_id=OuterRef("product_id"),
            price_list_id=OuterRef("effective_price_list_id"),
            active=True,
            price_list__active=True,
        )
        .values("amount")[:1]
    )
    queryset = queryset.annotate(
        catalog_price=Subquery(
            price_subquery,
            output_field=DecimalField(max_digits=10, decimal_places=2),
        )
    ).annotate(
        public_price=Coalesce(
            "catalog_price", "product__price_sale",
            output_field=DecimalField(max_digits=10, decimal_places=2),
        )
    )

    if warehouse_ids:
        stock_subquery = (
            StockByWarehouse.objects.filter(
                product_id=OuterRef("product_id"), warehouse_id__in=warehouse_ids
            )
            .values("product_id")
            .annotate(total=Sum("quantity"))
            .values("total")[:1]
        )
        queryset = queryset.annotate(
            public_stock=Coalesce(
                Subquery(
                    stock_subquery,
                    output_field=DecimalField(max_digits=14, decimal_places=3),
                ),
                Value(0),
                output_field=DecimalField(max_digits=14, decimal_places=3),
            )
        )
        if not catalog_settings.show_out_of_stock and not include_hidden_out_of_stock:
            queryset = queryset.filter(
                Q(product__tracks_inventory=False) | Q(public_stock__gt=0)
            )
    else:
        queryset = queryset.annotate(
            public_stock=Value(
                None, output_field=DecimalField(max_digits=14, decimal_places=3)
            )
        )

    return queryset
