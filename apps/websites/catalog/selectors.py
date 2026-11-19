"""SQL offers: authorized list only, live ERP data and bounded relation loading."""
from decimal import Decimal

from django.db.models import (
    BooleanField, Case, CharField, Count, DecimalField, ExpressionWrapper, F,
    OuterRef, Prefetch, Q, Subquery, Sum, UUIDField, Value, When,
)
from django.db.models.functions import Coalesce, NullIf, Round
from django.utils import timezone

from apps.inventory.models import Brand, Category, ProductPrice, ProductUnit, StockByWarehouse, Warehouse
from apps.inventory.pricing import tax_rate_for_company
from apps.websites.models import Website, WebsiteCatalogSettings, WebsiteProduct
from apps.websites.public_content import published_content


MONEY_FIELD = DecimalField(max_digits=30, decimal_places=2)
FACTOR_FIELD = DecimalField(max_digits=30, decimal_places=6)
_UNSET_CONFIGURATION = object()


def public_website(hostname):
    context = published_content(hostname)
    return Website.objects.get(pk=context["websiteId"], company__is_active=True, status=Website.Status.PUBLISHED)


def configured_warehouses(website, configuration):
    if configuration is None:
        return Warehouse.objects.none()
    return configuration.warehouses.filter(active=True, store__active=True, store__company_id=website.company_id)


def catalog_offers(website, *, detail=False, configuration=_UNSET_CONFIGURATION, customer_price_list=None):
    if configuration is _UNSET_CONFIGURATION:
        configuration = WebsiteCatalogSettings.objects.filter(website=website).first()
    warehouses = configured_warehouses(website, configuration)
    has_warehouses = warehouses.exists()
    default_list_id = configuration.default_price_list_id if configuration else None
    # The account service supplies this list only after current approval and
    # contact checks. It takes precedence over public product overrides.
    if customer_price_list is not None:
        from apps.websites.errors import WebsiteError
        if customer_price_list.company_id != website.company_id or not customer_price_list.active:
            raise WebsiteError("Lista comercial no autorizada.", code="CUSTOMER_PRICE_UNAVAILABLE", status=409)
    prices = ProductPrice.objects.filter(
        product_id=OuterRef("product_id"), price_list_id=OuterRef("offer_list_id"),
        active=True, price_list__active=True, price_list__company_id=website.company_id,
        currency=website.currency, amount__gte=0,
    )
    default_unit = ProductUnit.objects.filter(
        product_id=OuterRef("product_id"), active=True, is_default_sale=True, conversion_factor__gt=0,
    ).filter(~Q(unit_id=OuterRef("product__unit_id")) | Q(conversion_factor=1))
    stock = StockByWarehouse.objects.filter(
        product_id=OuterRef("product_id"), product__company_id=website.company_id,
        warehouse_id__in=warehouses.values("pk"),
    ).order_by().values("product_id").annotate(total=Sum("quantity")).values("total")[:1]
    rate = tax_rate_for_company(website.company_id, on_date=timezone.localdate())
    queryset = WebsiteProduct.objects.filter(
        website=website, is_published=True, product__active=True, product__company_id=website.company_id,
    ).select_related("product__unit", "product__category", "product__brand").annotate(
        offer_name=Coalesce(NullIf(F("commercial_title"), Value("")), F("product__name")),
        offer_list_id=Value(customer_price_list.pk, output_field=UUIDField()) if customer_price_list is not None else Coalesce(F("price_list_id"), Value(default_list_id, output_field=UUIDField()), output_field=UUIDField()),
        offer_factor=Coalesce(Subquery(default_unit.values("conversion_factor")[:1]), Value(Decimal("1")), output_field=FACTOR_FIELD),
        offer_unit_id=Coalesce(Subquery(default_unit.values("unit_id")[:1]), F("product__unit_id"), output_field=UUIDField()),
        offer_unit=Coalesce(Subquery(default_unit.values("unit__name")[:1]), F("product__unit__name")),
        offer_stock=Coalesce(Subquery(stock), Value(Decimal("0")), output_field=FACTOR_FIELD),
        public_category_id=Case(When(product__category__company_id=website.company_id, product__category__active=True, then=F("product__category_id")), default=None, output_field=UUIDField()),
        public_brand_id=Case(When(product__brand__company_id=website.company_id, product__brand__active=True, then=F("product__brand_id")), default=None, output_field=UUIDField()),
        offer_amount=Subquery(prices.values("amount")[:1]),
        offer_includes_tax=Coalesce(Subquery(prices.values("price_list__prices_include_tax")[:1]), Value(True), output_field=BooleanField()),
    ).annotate(
        offer_tax_multiplier=Case(
            When(offer_includes_tax=False, product__tax_affectation="10", then=Value(Decimal("1") + rate / Decimal("100"))),
            default=Value(Decimal("1")), output_field=FACTOR_FIELD,
        ),
        offer_availability=Case(
            When(product__tracks_inventory=False, then=Value("unknown")),
            When(offer_stock__gte=F("offer_factor"), then=Value("available")),
            default=Value("unavailable"), output_field=CharField(),
        ) if has_warehouses else Value("unknown", output_field=CharField()),
    ).annotate(
        offer_price=Round(ExpressionWrapper(F("offer_amount") * F("offer_factor") * F("offer_tax_multiplier"), output_field=MONEY_FIELD), 2),
    )
    if configuration and not configuration.show_out_of_stock:
        queryset = queryset.exclude(offer_availability="unavailable")
    if detail:
        queryset = queryset.prefetch_related(Prefetch(
            "product__unit_conversions", queryset=ProductUnit.objects.filter(active=True, conversion_factor__gt=0).select_related("unit"),
            to_attr="catalog_sale_units",
        ))
    return queryset


def filter_offers(queryset, filters, *, exclude_group=None):
    if filters.get("search"):
        queryset = queryset.filter(Q(offer_name__icontains=filters["search"]) | Q(product__sku__icontains=filters["search"]))
    for group in ("category", "brand"):
        if group != exclude_group and filters.get(group):
            queryset = queryset.filter(**{f"public_{group}_id__in": filters[group]})
    if filters.get("min") is not None:
        queryset = queryset.filter(offer_price__gte=filters["min"])
    if filters.get("max") is not None:
        queryset = queryset.filter(offer_price__lte=filters["max"])
    if "featured" in filters:
        queryset = queryset.filter(is_featured=filters["featured"])
    return queryset


def order_offers(queryset, ordering):
    orders = {
        "name": (F("offer_name").asc(), "product_id"),
        "name-desc": (F("offer_name").desc(), "product_id"),
        "price-asc": (F("offer_price").asc(nulls_last=True), "product_id"),
        "price-desc": (F("offer_price").desc(nulls_last=True), "product_id"),
        "featured": ("-is_featured", "position", "product_id"),
    }
    return queryset.order_by(*orders[ordering])


def facet_rows(queryset, website, group):
    key = f"public_{group}_id"
    counts = dict(queryset.order_by().exclude(**{key: None}).values(key).annotate(total=Count("pk")).values_list(key, "total"))
    model = Category if group == "category" else Brand
    return [
        {"id": str(item.pk), "name": item.name, "productCount": counts[item.pk], **({"parent_id": None} if group == "category" else {})}
        for item in model.objects.filter(company_id=website.company_id, active=True, pk__in=counts).order_by("name", "pk")
    ]
