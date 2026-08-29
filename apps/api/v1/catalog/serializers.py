from rest_framework import serializers

from apps.inventory.models import Product


class ProductImageSerializerMixin(serializers.Serializer):
    image = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    supplier_codes = serializers.SerializerMethodField()

    def get_image(self, obj):
        return obj.image

    def get_images(self, obj):
        return obj.image_urls

    def get_supplier_codes(self, obj):
        relations = getattr(obj, "active_supplier_code_relations", ())
        return list(dict.fromkeys(relation.supplier_code for relation in relations))


class CatalogProductListSerializer(ProductImageSerializerMixin, serializers.ModelSerializer):
    unit = serializers.CharField(source="unit.code", read_only=True)
    brand = serializers.CharField(source="brand.name", read_only=True)
    category = serializers.CharField(source="category.name", read_only=True)
    stock = serializers.FloatField(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id", "name", "sku", "unit", "brand", "category",
            "price_sale", "price_purchase", "stock", "image", "images", "supplier_codes",
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
            "supplier_codes",
            "brand",
            "category",
            "price_sale",
            "price_purchase",
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
        prices = obj.prices.filter(active=True).select_related("price_list").order_by("price_list__name")
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
