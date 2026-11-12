from rest_framework import serializers

from apps.websites.models import (
    Website,
    WebsiteDomain,
    WebsiteSettings,
    WebsitePage,
    WebsiteSection,
    WebsiteMedia,
    WebsiteMenu,
    WebsiteMenuItem,
    WebsiteCatalogSettings,
    WebsiteProduct,
    is_reserved_hostname,
    normalize_hostname,
)
from apps.inventory.models import PriceList, Product, Warehouse
from apps.websites.blocks import validate_block_config
from django.core.exceptions import ValidationError as DjangoValidationError


class WebsiteSettingsSerializer(serializers.ModelSerializer):
    logo_media_url = serializers.SerializerMethodField()
    favicon_media_url = serializers.SerializerMethodField()
    class Meta:
        model = WebsiteSettings
        fields = (
            "business_name",
            "logo_url",
            "favicon_url",
            "primary_color",
            "accent_color",
            "background_color",
            "text_color",
            "whatsapp",
            "phone",
            "email",
            "address",
            "business_hours",
            "social_links",
            "default_seo_title",
            "default_seo_description",
            "default_noindex",
            "heading_font",
            "body_font",
            "border_radius",
            "footer_text",
            "google_maps_url",
            "logo_media",
            "logo_media_url",
            "favicon_media",
            "favicon_media_url",
            "updated_at",
        )
        read_only_fields = ("updated_at",)

    def get_logo_media_url(self, obj):
        return obj.logo_media.url if obj.logo_media and not obj.logo_media.is_deleted else ""

    def get_favicon_media_url(self, obj):
        return obj.favicon_media.url if obj.favicon_media and not obj.favicon_media.is_deleted else ""

    def validate(self, attrs):
        website_id = self.instance.website_id if self.instance else None
        for field in ("logo_media", "favicon_media"):
            media = attrs.get(field)
            if media and (media.website_id != website_id or media.is_deleted):
                raise serializers.ValidationError({field: "El medio no pertenece al sitio web activo."})
        return attrs

    def validate_social_links(self, value):
        allowed = {"facebook", "instagram", "youtube", "tiktok", "linkedin"}
        unknown = set(value or {}) - allowed
        if unknown:
            raise serializers.ValidationError(
                f"Redes no permitidas: {', '.join(sorted(unknown))}."
            )
        url_field = serializers.URLField()
        return {key: url_field.run_validation(url) for key, url in (value or {}).items()}


class WebsiteDomainSerializer(serializers.ModelSerializer):
    verification_token = serializers.CharField(read_only=True)
    dns_record_name = serializers.SerializerMethodField()

    class Meta:
        model = WebsiteDomain
        fields = (
            "id",
            "hostname",
            "kind",
            "status",
            "is_primary",
            "verification_method",
            "verification_token",
            "dns_record_name",
            "verified_at",
            "last_verification_error",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "status",
            "is_primary",
            "verification_method",
            "verified_at",
            "last_verification_error",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {"hostname": {"validators": []}}

    def validate_hostname(self, value):
        value = normalize_hostname(value)
        if is_reserved_hostname(value):
            raise serializers.ValidationError("Este hostname estÃ¡ reservado por APUDIG.")
        return value

    def get_dns_record_name(self, obj) -> str:
        return f"_apudig-verification.{obj.hostname}"

    def to_representation(self, instance):
        data = super().to_representation(instance)
        token = getattr(instance, "_verification_token", None)
        if token:
            data["verification_token"] = token
        else:
            data.pop("verification_token", None)
        return data


class WebsiteSerializer(serializers.ModelSerializer):
    domains = WebsiteDomainSerializer(many=True, read_only=True)

    class Meta:
        model = Website
        fields = (
            "id",
            "name",
            "template_key",
            "template_schema_version",
            "slug",
            "status",
            "default_locale",
            "timezone",
            "currency",
            "published_at",
            "domains",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "slug",
            "template_key",
            "template_schema_version",
            "status",
            "published_at",
            "domains",
            "created_at",
            "updated_at",
        )

    def validate_currency(self, value):
        value = value.upper()
        if len(value) != 3 or not value.isalpha():
            raise serializers.ValidationError("Use un cÃ³digo ISO 4217 de tres letras.")
        return value

    def validate_default_locale(self, value):
        if not value or len(value) > 15:
            raise serializers.ValidationError("Ingrese un locale vÃ¡lido.")
        return value


class WebsiteCatalogSettingsSerializer(serializers.ModelSerializer):
    price_list_options = serializers.SerializerMethodField()
    warehouse_options = serializers.SerializerMethodField()

    class Meta:
        model = WebsiteCatalogSettings
        fields = (
            "default_price_list", "warehouses", "show_out_of_stock",
            "products_per_page", "price_list_options", "warehouse_options",
            "updated_at",
        )
        read_only_fields = ("price_list_options", "warehouse_options", "updated_at")

    def get_price_list_options(self, obj):
        return [
            {"id": str(item.pk), "name": item.name, "is_default": item.is_default}
            for item in PriceList.objects.filter(
                company_id=obj.website.company_id, active=True
            ).order_by("-is_default", "name")
        ]

    def get_warehouse_options(self, obj):
        return [
            {"id": str(item.pk), "name": item.name, "store": item.store.name}
            for item in Warehouse.objects.filter(
                store__company_id=obj.website.company_id, active=True
            ).select_related("store").order_by("store__name", "name")
        ]

    def validate(self, attrs):
        website = self.instance.website
        price_list = attrs.get("default_price_list")
        if price_list and price_list.company_id != website.company_id:
            raise serializers.ValidationError({
                "default_price_list": "La lista de precios no pertenece a la empresa activa."
            })
        warehouses = attrs.get("warehouses")
        if warehouses and any(
            warehouse.store.company_id != website.company_id for warehouse in warehouses
        ):
            raise serializers.ValidationError({
                "warehouses": "Todos los almacenes deben pertenecer a la empresa activa."
            })
        return attrs

    def validate_products_per_page(self, value):
        if not 1 <= value <= 60:
            raise serializers.ValidationError("Use un valor entre 1 y 60.")
        return value


class WebsiteProductSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    sku = serializers.CharField(source="product.sku", read_only=True)
    category = serializers.CharField(source="product.category.name", read_only=True, allow_null=True)
    brand = serializers.CharField(source="product.brand.name", read_only=True, allow_null=True)
    thumbnail = serializers.CharField(source="product.image_thumbnail", read_only=True)

    class Meta:
        model = WebsiteProduct
        fields = (
            "id", "product", "product_name", "sku", "category", "brand",
            "thumbnail", "price_list", "slug", "commercial_title",
            "commercial_description", "seo_title", "seo_description",
            "is_published", "is_featured", "position", "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "product_name", "sku", "category", "brand", "thumbnail",
            "created_at", "updated_at",
        )
        extra_kwargs = {"slug": {"required": False, "allow_blank": True}}

    def validate(self, attrs):
        website = self.context["website"]
        product = attrs.get("product", getattr(self.instance, "product", None))
        price_list = attrs.get("price_list", getattr(self.instance, "price_list", None))
        if not product or product.company_id != website.company_id:
            raise serializers.ValidationError({
                "product": "El producto no pertenece a la empresa activa."
            })
        if self.instance and "product" in attrs and product.pk != self.instance.product_id:
            raise serializers.ValidationError({
                "product": "El producto del vínculo no puede cambiarse."
            })
        if price_list and price_list.company_id != website.company_id:
            raise serializers.ValidationError({
                "price_list": "La lista de precios no pertenece a la empresa activa."
            })
        return attrs


class WebsiteCatalogProductOptionSerializer(serializers.ModelSerializer):
    category = serializers.CharField(source="category.name", read_only=True, allow_null=True)
    brand = serializers.CharField(source="brand.name", read_only=True, allow_null=True)
    thumbnail = serializers.CharField(source="image_thumbnail", read_only=True)

    class Meta:
        model = Product
        fields = ("id", "name", "sku", "category", "brand", "thumbnail")


class WebsiteSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebsiteSection
        fields = ("id", "section_type", "schema_version", "position", "enabled", "config")
        read_only_fields = ("id",)

    def validate(self, attrs):
        try:
            attrs["config"] = validate_block_config(
                attrs.get("section_type"), attrs.get("schema_version", 1), attrs.get("config", {})
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages) from exc
        return attrs


class WebsitePageSerializer(serializers.ModelSerializer):
    sections = WebsiteSectionSerializer(many=True, read_only=True)

    class Meta:
        model = WebsitePage
        fields = (
            "id", "slug", "title", "page_type", "status", "seo_title",
            "seo_description", "og_image_url", "noindex", "draft_version",
            "published_version", "published_at", "sections", "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "status", "draft_version", "published_version", "published_at",
            "sections", "created_at", "updated_at",
        )

    def validate_page_type(self, value):
        if self.instance and value != self.instance.page_type:
            raise serializers.ValidationError("El tipo de página no puede cambiar después de crearla.")
        return value

    def update(self, instance, validated_data):
        changed = any(getattr(instance, field) != value for field, value in validated_data.items())
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if changed:
            instance.draft_version += 1
        instance.updated_by = self.context["request"].user
        instance.save()
        return instance


class ReplaceSectionsSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    sections = WebsiteSectionSerializer(many=True)

    def validate_sections(self, value):
        for position, section in enumerate(value):
            if section["position"] != position:
                raise serializers.ValidationError("Las posiciones deben ser consecutivas y comenzar en cero.")
        return value


class PublishPageSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)


class WebsiteMediaSerializer(serializers.ModelSerializer):
    url = serializers.CharField(read_only=True)
    thumbnail_url = serializers.CharField(read_only=True)

    class Meta:
        model = WebsiteMedia
        fields = (
            "id", "kind", "original_name", "alt_text", "mime_type", "size",
            "width", "height", "url", "thumbnail_url", "created_at",
        )
        read_only_fields = fields


class WebsiteMediaUploadSerializer(serializers.Serializer):
    file = serializers.ImageField()
    kind = serializers.ChoiceField(choices=WebsiteMedia.Kind.choices, default=WebsiteMedia.Kind.IMAGE)
    alt_text = serializers.CharField(max_length=180, allow_blank=True, required=False, default="")


class WebsiteMenuItemSerializer(serializers.ModelSerializer):
    page_id = serializers.UUIDField(source="page.id", allow_null=True, read_only=True)
    parent_id = serializers.UUIDField(source="parent.id", allow_null=True, read_only=True)

    class Meta:
        model = WebsiteMenuItem
        fields = (
            "id", "parent_id", "position", "label", "target_type", "page_id",
            "url", "open_in_new_tab", "enabled",
        )


class WebsiteMenuSerializer(serializers.ModelSerializer):
    items = WebsiteMenuItemSerializer(many=True, read_only=True)

    class Meta:
        model = WebsiteMenu
        fields = (
            "id", "name", "location", "status", "enabled", "draft_version",
            "published_version", "published_at", "items", "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "status", "draft_version", "published_version", "published_at",
            "items", "created_at", "updated_at",
        )


class WebsiteMenuItemInputSerializer(serializers.Serializer):
    parent_index = serializers.IntegerField(min_value=0, allow_null=True, required=False, default=None)
    position = serializers.IntegerField(min_value=0)
    label = serializers.CharField(max_length=80)
    target_type = serializers.ChoiceField(choices=WebsiteMenuItem.TargetType.choices)
    page_id = serializers.UUIDField(allow_null=True, required=False)
    url = serializers.CharField(max_length=1000, allow_blank=True, required=False, default="")
    open_in_new_tab = serializers.BooleanField(required=False, default=False)
    enabled = serializers.BooleanField(required=False, default=True)


class ReplaceMenuItemsSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    items = WebsiteMenuItemInputSerializer(many=True)


class PublishMenuSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
