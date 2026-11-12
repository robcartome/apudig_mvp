from rest_framework import serializers

from apps.inventory.models import Product
from apps.websites.models import WebsiteProduct


class StorefrontLogoSerializer(serializers.Serializer):
    url = serializers.URLField(allow_blank=True)
    alt = serializers.CharField(allow_blank=True)


class StorefrontThemeSerializer(serializers.Serializer):
    primary_color = serializers.CharField()
    accent_color = serializers.CharField()
    background_color = serializers.CharField()
    text_color = serializers.CharField()
    logo = StorefrontLogoSerializer()
    favicon_url = serializers.URLField(allow_blank=True)
    heading_font = serializers.CharField()
    body_font = serializers.CharField()
    border_radius = serializers.IntegerField()


class StorefrontContactSerializer(serializers.Serializer):
    whatsapp = serializers.CharField(allow_blank=True)
    phone = serializers.CharField(allow_blank=True)
    email = serializers.EmailField(allow_blank=True)
    address = serializers.CharField(allow_blank=True)
    business_hours = serializers.DictField()
    social_links = serializers.DictField()
    google_maps_url = serializers.URLField(allow_blank=True)


class StorefrontResolveSerializer(serializers.Serializer):
    website_id = serializers.UUIDField()
    template_key = serializers.CharField()
    template_schema_version = serializers.IntegerField()
    hostname = serializers.CharField()
    canonical_url = serializers.URLField()
    canonical_hostname = serializers.CharField()
    is_primary = serializers.BooleanField()
    name = serializers.CharField()
    locale = serializers.CharField()
    currency = serializers.CharField()
    theme = StorefrontThemeSerializer()
    contact = StorefrontContactSerializer()
    seo = serializers.DictField()
    menus = serializers.DictField()
    footer_text = serializers.CharField(allow_blank=True)
    publication_version = serializers.IntegerField()
    catalog = serializers.DictField()


class ProductImageSerializerMixin(serializers.Serializer):
    image = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()
    thumbnails = serializers.SerializerMethodField()
    supplier_codes = serializers.SerializerMethodField()
    price_includes_tax = serializers.SerializerMethodField()
    tax_rate = serializers.SerializerMethodField()

    def get_image(self, obj):
        return obj.image

    def get_images(self, obj):
        return obj.image_urls

    def get_thumbnail(self, obj):
        return obj.image_thumbnail

    def get_thumbnails(self, obj):
        return obj.thumbnail_urls

    def get_supplier_codes(self, obj):
        relations = getattr(obj, "active_supplier_code_relations", ())
        return list(dict.fromkeys(relation.supplier_code for relation in relations))

    def get_price_includes_tax(self, obj):
        return True

    def get_tax_rate(self, obj):
        if obj.tax_affectation != "10":
            return "0.00"
        cache = self.context.setdefault("_tax_rate_cache", {})
        key = str(obj.company_id)
        if key not in cache:
            from apps.inventory.pricing import tax_rate_for_company
            cache[key] = tax_rate_for_company(obj.company_id, affectation_type=obj.tax_affectation)
        return str(cache[key])


class CatalogProductListSerializer(ProductImageSerializerMixin, serializers.ModelSerializer):
    unit = serializers.CharField(source="unit.code", read_only=True)
    brand = serializers.CharField(source="brand.name", read_only=True)
    category = serializers.CharField(source="category.name", read_only=True)
    stock = serializers.FloatField(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id", "name", "sku", "unit", "brand", "category",
            "price_sale", "price_purchase", "price_includes_tax", "tax_affectation", "tax_rate",
            "stock", "image", "images", "thumbnail", "thumbnails", "supplier_codes",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self.context.get("include_purchase_price"):
            data.pop("price_purchase", None)
        return data


class CatalogProductPriceListSerializer(serializers.Serializer):
    price_list_name = serializers.CharField(source="price_list.name")
    amount = serializers.CharField()
    currency = serializers.CharField()
    price_includes_tax = serializers.BooleanField(source="price_list.prices_include_tax")


class CatalogProductStockByWarehouseSerializer(serializers.Serializer):
    warehouse_name = serializers.CharField()
    location = serializers.CharField(allow_null=True)
    quantity = serializers.FloatField()


class CatalogProductDetailSerializer(ProductImageSerializerMixin, serializers.ModelSerializer):
    unit = serializers.CharField(source="unit.code", read_only=True)
    brand = serializers.CharField(source="brand.name", read_only=True)
    category = serializers.CharField(source="category.name", read_only=True)
    price_list = serializers.SerializerMethodField()
    stock_total = serializers.SerializerMethodField()
    stock_by_warehouse = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "sku",
            "unit",
            "description",
            "image",
            "images",
            "thumbnail",
            "thumbnails",
            "supplier_codes",
            "brand",
            "category",
            "price_sale",
            "price_purchase",
            "price_includes_tax",
            "tax_affectation",
            "tax_rate",
            "price_list",
            "stock_total",
            "stock_by_warehouse",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self.context.get("include_purchase_price"):
            data.pop("price_purchase", None)
        return data

    def get_price_list(self, obj):
        prices = obj.prices.filter(active=True, price_list__active=True).select_related("price_list").order_by("price_list__name")
        return CatalogProductPriceListSerializer(prices, many=True).data

    def get_stock_total(self, obj):
        total = sum((row.quantity or 0) for row in obj.stocks.all())
        return float(total)

    def get_stock_by_warehouse(self, obj):
        rows = obj.stocks.select_related("warehouse").order_by("warehouse__name")
        return [
            {
                "warehouse_name": row.warehouse.name if row.warehouse else "",
                "location": row.location or None,
                "quantity": float(row.quantity or 0),
            }
            for row in rows
        ]


class StorefrontProductImageSerializerMixin(serializers.Serializer):
    """Public image and tax fields without supplier or inventory metadata."""

    image = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()
    thumbnails = serializers.SerializerMethodField()
    price_includes_tax = serializers.SerializerMethodField()
    tax_rate = serializers.SerializerMethodField()

    def get_image(self, obj) -> str | None:
        return obj.image

    def get_images(self, obj) -> list[str]:
        return obj.image_urls

    def get_thumbnail(self, obj) -> str | None:
        return obj.image_thumbnail

    def get_thumbnails(self, obj) -> list[str]:
        return obj.thumbnail_urls

    def get_price_includes_tax(self, obj) -> bool:
        return True

    def get_tax_rate(self, obj) -> str:
        if obj.tax_affectation != "10":
            return "0.00"
        cache = self.context.setdefault("_tax_rate_cache", {})
        key = str(obj.company_id)
        if key not in cache:
            from apps.inventory.pricing import tax_rate_for_company
            cache[key] = tax_rate_for_company(
                obj.company_id,
                affectation_type=obj.tax_affectation,
            )
        return str(cache[key])


class StorefrontProductListSerializer(
    StorefrontProductImageSerializerMixin,
    serializers.ModelSerializer,
):
    unit = serializers.CharField(source="unit.code", read_only=True)
    brand = serializers.CharField(source="brand.name", read_only=True)
    category = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Product
        fields = (
            "id", "name", "sku", "unit", "brand", "category",
            "price_sale", "price_includes_tax", "tax_affectation", "tax_rate",
            "image", "images", "thumbnail", "thumbnails",
        )


class StorefrontProductDetailSerializer(
    StorefrontProductImageSerializerMixin,
    serializers.ModelSerializer,
):
    unit = serializers.CharField(source="unit.code", read_only=True)
    brand = serializers.CharField(source="brand.name", read_only=True)
    category = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Product
        fields = (
            "id", "name", "sku", "unit", "description", "brand", "category",
            "price_sale", "price_includes_tax", "tax_affectation", "tax_rate",
            "image", "images", "thumbnail", "thumbnails",
        )


class PublishedWebsiteProductSerializer(serializers.ModelSerializer):
    """Strict public contract for an explicitly published website product."""

    id = serializers.UUIDField(source="product_id", read_only=True)
    name = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    sku = serializers.CharField(source="product.sku", read_only=True)
    unit = serializers.CharField(source="product.unit.code", read_only=True)
    brand = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    price_includes_tax = serializers.SerializerMethodField()
    tax_rate = serializers.SerializerMethodField()
    availability = serializers.SerializerMethodField()
    available = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()
    thumbnails = serializers.SerializerMethodField()
    featured = serializers.BooleanField(source="is_featured", read_only=True)

    class Meta:
        model = WebsiteProduct
        fields = (
            "id", "slug", "name", "description", "sku", "unit", "brand",
            "category", "price", "currency", "price_includes_tax", "tax_rate",
            "availability", "available", "image", "images", "thumbnail",
            "thumbnails", "featured", "seo_title", "seo_description",
        )

    def get_name(self, obj):
        return obj.public_name

    def get_description(self, obj):
        return obj.public_description

    def get_brand(self, obj):
        brand = obj.product.brand
        return {"id": str(brand.pk), "name": brand.name} if brand else None

    def get_category(self, obj):
        category = obj.product.category
        return {"id": str(category.pk), "name": category.name} if category else None

    def get_price(self, obj):
        return str(obj.public_price)

    def get_currency(self, obj):
        website = self.context.get("website") or obj.website
        return website.currency

    def get_price_includes_tax(self, obj):
        if obj.price_list_id:
            return obj.price_list.prices_include_tax
        catalog_settings = self.context.get("catalog_settings")
        if catalog_settings and catalog_settings.default_price_list_id:
            return catalog_settings.default_price_list.prices_include_tax
        return True

    def get_tax_rate(self, obj):
        if obj.product.tax_affectation != "10":
            return "0.00"
        cache = self.context.setdefault("_tax_rate_cache", {})
        key = str(obj.website.company_id)
        if key not in cache:
            from apps.inventory.pricing import tax_rate_for_company
            cache[key] = tax_rate_for_company(
                obj.website.company_id,
                affectation_type=obj.product.tax_affectation,
            )
        return str(cache[key])

    def get_availability(self, obj):
        if not obj.product.tracks_inventory:
            return "AVAILABLE"
        stock = getattr(obj, "public_stock", None)
        if stock is None:
            return "UNKNOWN"
        return "AVAILABLE" if stock > 0 else "OUT_OF_STOCK"

    def get_available(self, obj):
        availability = self.get_availability(obj)
        if availability == "UNKNOWN":
            return None
        return availability == "AVAILABLE"

    def get_image(self, obj):
        return obj.product.image

    def get_images(self, obj):
        return obj.product.image_urls

    def get_thumbnail(self, obj):
        return obj.product.image_thumbnail

    def get_thumbnails(self, obj):
        return obj.product.thumbnail_urls


class StorefrontTaxonomySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    product_count = serializers.IntegerField()


class StorefrontCartLineSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=999)


class StorefrontCartQuoteRequestSerializer(serializers.Serializer):
    lines = StorefrontCartLineSerializer(many=True, allow_empty=False, max_length=50)

    def validate_lines(self, value):
        product_ids = [line["product_id"] for line in value]
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError("No repita productos; actualice su cantidad.")
        return value


class StorefrontCartQuoteLineSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=("ACTIVE", "REMOVED", "OUT_OF_STOCK"))
    quantity = serializers.IntegerField()
    slug = serializers.CharField(required=False)
    sku = serializers.CharField(required=False)
    name = serializers.CharField(required=False)
    unit = serializers.CharField(required=False)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    subtotal = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    availability = serializers.CharField(required=False)
    image = serializers.URLField(required=False, allow_blank=True)


class StorefrontCartQuoteSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    quote_id = serializers.UUIDField()
    quote_token = serializers.CharField()
    quoted_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    currency = serializers.CharField()
    total = serializers.DecimalField(max_digits=14, decimal_places=2)
    has_changes = serializers.BooleanField()
    can_submit = serializers.BooleanField()
    lines = StorefrontCartQuoteLineSerializer(many=True)
