from rest_framework import serializers

from apps.inventory.models import Product


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
