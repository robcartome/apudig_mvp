from datetime import timezone

from rest_framework import serializers

from apps.api.v1.websites.serializers import StrictSerializer


class CatalogErrorSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    fields = serializers.DictField(child=serializers.CharField(), required=False)


class PageQuerySerializer(StrictSerializer):
    limit = serializers.IntegerField(min_value=1, max_value=100, required=False)
    offset = serializers.IntegerField(min_value=0, max_value=2**31 - 1, default=0)


class SearchPageQuerySerializer(PageQuerySerializer):
    search = serializers.CharField(max_length=120, allow_blank=True, default="")


class ProductQuerySerializer(SearchPageQuerySerializer):
    category = serializers.ListField(child=serializers.UUIDField(), max_length=50, required=False)
    brand = serializers.ListField(child=serializers.UUIDField(), max_length=50, required=False)
    min = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=0, required=False)
    max = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=0, required=False)
    ordering = serializers.ChoiceField(choices=("name", "name-desc", "price-asc", "price-desc", "featured"), default="name")
    featured = serializers.BooleanField(required=False)

    def validate(self, data):
        if data.get("min") is not None and data.get("max") is not None and data["min"] > data["max"]:
            raise serializers.ValidationError({"max": "Debe ser mayor o igual al precio mínimo."})
        return data


class CatalogSettingsPatchSerializer(StrictSerializer):
    commerceEnabled = serializers.BooleanField(required=False)

    def validate_commerceEnabled(self, value):
        if type(self.initial_data.get("commerceEnabled")) is not bool:
            raise serializers.ValidationError("Selecciona expresamente habilitar o deshabilitar solicitudes.")
        return value
    defaultPriceListId = serializers.UUIDField(allow_null=True, required=False)
    warehouseIds = serializers.ListField(child=serializers.UUIDField(), max_length=100, required=False)
    showOutOfStock = serializers.BooleanField(required=False)
    productsPerPage = serializers.IntegerField(min_value=1, max_value=60, required=False)

    def validate_warehouseIds(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("No repitas almacenes.")
        return value


class PublicationPatchSerializer(StrictSerializer):
    isPublished = serializers.BooleanField(required=False)
    isFeatured = serializers.BooleanField(required=False)
    position = serializers.IntegerField(min_value=0, max_value=2**31 - 1, required=False)
    priceListId = serializers.UUIDField(allow_null=True, required=False)
    commercialTitle = serializers.CharField(max_length=180, allow_blank=True, required=False)
    commercialDescription = serializers.CharField(max_length=1000, allow_blank=True, required=False)
    seoTitle = serializers.CharField(max_length=70, allow_blank=True, required=False)
    seoDescription = serializers.CharField(max_length=170, allow_blank=True, required=False)


class PublicationCreateSerializer(PublicationPatchSerializer):
    productId = serializers.UUIDField()


class NamedPublicRelationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class PublicSaleUnitSerializer(serializers.Serializer):
    unitId = serializers.UUIDField()
    unit = serializers.CharField()
    price = serializers.CharField(allow_null=True)
    availability = serializers.ChoiceField(choices=("unknown", "available", "unavailable"))


class PublicProductSerializer(PublicSaleUnitSerializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    sku = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    brand = NamedPublicRelationSerializer(allow_null=True)
    category = NamedPublicRelationSerializer(allow_null=True)
    currency = serializers.CharField()
    priceIncludesTax = serializers.BooleanField()
    original_price = serializers.CharField(allow_null=True)
    image_url = serializers.CharField(allow_null=True, allow_blank=True)
    image_alt = serializers.CharField()
    images = serializers.ListField(child=serializers.CharField())
    badge = serializers.CharField(allow_blank=True)


class PublicProductDetailSerializer(PublicProductSerializer):
    saleUnits = PublicSaleUnitSerializer(many=True)
    seoTitle = serializers.CharField(allow_blank=True)
    seoDescription = serializers.CharField(allow_blank=True)


class PublicCategorySerializer(NamedPublicRelationSerializer):
    parent_id = serializers.UUIDField(allow_null=True)
    productCount = serializers.IntegerField()


class PublicBrandSerializer(NamedPublicRelationSerializer):
    productCount = serializers.IntegerField()


class ProductFacetsSerializer(serializers.Serializer):
    categories = PublicCategorySerializer(many=True)
    brands = PublicBrandSerializer(many=True)


class PublicProductsPageSerializer(serializers.Serializer):
    websiteId = serializers.UUIDField()
    count = serializers.IntegerField()
    limit = serializers.IntegerField()
    offset = serializers.IntegerField()
    results = PublicProductSerializer(many=True)
    facets = ProductFacetsSerializer()


class PublicProductResponseSerializer(serializers.Serializer):
    websiteId = serializers.UUIDField()
    product = PublicProductDetailSerializer()


class PublicCategoriesPageSerializer(serializers.Serializer):
    websiteId = serializers.UUIDField()
    count = serializers.IntegerField()
    limit = serializers.IntegerField()
    offset = serializers.IntegerField()
    results = PublicCategorySerializer(many=True)


class PublicBrandsPageSerializer(PublicCategoriesPageSerializer):
    results = PublicBrandSerializer(many=True)


class ProductOptionSerializer(serializers.Serializer):
    productId = serializers.UUIDField()
    name = serializers.CharField()
    sku = serializers.CharField()
    unitId = serializers.UUIDField()
    unit = serializers.CharField()


class ProductOptionsPageSerializer(PublicCategoriesPageSerializer):
    results = ProductOptionSerializer(many=True)


class OmitAbsentPolicyFieldsSerializer(serializers.Serializer):
    def to_representation(self, instance):
        data = super().to_representation(instance)
        return {key: value for key, value in data.items() if key in instance}


class PublicationSerializer(OmitAbsentPolicyFieldsSerializer):
    id = serializers.UUIDField()
    productId = serializers.UUIDField()
    slug = serializers.CharField()
    commercialTitle = serializers.CharField(allow_blank=True)
    commercialDescription = serializers.CharField(allow_blank=True)
    seoTitle = serializers.CharField(allow_blank=True)
    seoDescription = serializers.CharField(allow_blank=True)
    isPublished = serializers.BooleanField()
    isFeatured = serializers.BooleanField()
    position = serializers.IntegerField()
    priceListId = serializers.UUIDField(allow_null=True, required=False)
    updatedAt = serializers.DateTimeField(default_timezone=timezone.utc)


class PublicationsPageSerializer(PublicCategoriesPageSerializer):
    results = PublicationSerializer(many=True)


class PriceListOptionSerializer(NamedPublicRelationSerializer):
    pricesIncludeTax = serializers.BooleanField()


class WarehouseOptionSerializer(NamedPublicRelationSerializer):
    storeId = serializers.UUIDField()


class CatalogSettingsSerializer(OmitAbsentPolicyFieldsSerializer):
    websiteId = serializers.UUIDField()
    currency = serializers.CharField()
    commerceEnabled = serializers.BooleanField()
    commerceReady = serializers.BooleanField(required=False)
    commerceBlockers = serializers.ListField(child=serializers.DictField(child=serializers.CharField()), required=False)
    showOutOfStock = serializers.BooleanField()
    productsPerPage = serializers.IntegerField()
    canManagePolicy = serializers.BooleanField()
    defaultPriceListId = serializers.UUIDField(allow_null=True, required=False)
    warehouseIds = serializers.ListField(child=serializers.UUIDField(), required=False)
    priceListOptions = PriceListOptionSerializer(many=True, required=False)
    warehouseOptions = WarehouseOptionSerializer(many=True, required=False)
