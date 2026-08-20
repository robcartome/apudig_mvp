from django.db.models import Sum
from rest_framework import serializers

from apps.inventory.models import Brand, Category, Product, ProductPrice, StockByWarehouse
from apps.inventory.models import Unit, Warehouse
from apps.partners.models import DocumentType


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ("id", "name", "active")


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "code", "name", "active")


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ("id", "code", "name")


class WarehouseSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source="store.name", read_only=True)

    class Meta:
        model = Warehouse
        fields = ("id", "store", "store_name", "name", "description", "active", "is_default")


class WarehouseUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ("name", "description", "active", "is_default")


class DocumentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentType
        fields = (
            "id", "code", "name", "abbreviation", "category", "is_sunat",
            "sunat_code", "affects_stock", "affects_accounting", "active",
        )


class ProductPriceSerializer(serializers.ModelSerializer):
    price_list_name = serializers.CharField(source="price_list.name", read_only=True)

    class Meta:
        model = ProductPrice
        fields = ("id", "price_list", "price_list_name", "amount", "currency", "active")


class StockByWarehouseSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)

    class Meta:
        model = StockByWarehouse
        fields = ("warehouse_name", "location", "quantity")


class ProductListSerializer(serializers.ModelSerializer):
    unit = serializers.CharField(source="unit.code", read_only=True)
    brand = serializers.CharField(source="brand.name", read_only=True)
    category = serializers.CharField(source="category.name", read_only=True)
    stock = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "sku",
            "unit",
            "brand",
            "category",
            "price_sale",
            "price_purchase",
            "stock",
            "image",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            data.pop("price_purchase", None)
        return data


class ProductDetailSerializer(serializers.ModelSerializer):
    unit = serializers.CharField(source="unit.code", read_only=True)
    brand = serializers.CharField(source="brand.name", read_only=True)
    category = serializers.CharField(source="category.name", read_only=True)
    price_list = ProductPriceSerializer(source="prices", many=True, read_only=True)
    stock_total = serializers.SerializerMethodField()
    stock_by_warehouse = StockByWarehouseSerializer(source="stocks", many=True, read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "sku",
            "unit",
            "description",
            "image",
            "brand",
            "category",
            "price_sale",
            "price_purchase",
            "price_list",
            "stock_total",
            "stock_by_warehouse",
        )

    def get_stock_total(self, obj):
        total = obj.stocks.aggregate(total=Sum("quantity")).get("total")
        return total or 0

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            data.pop("price_purchase", None)
        return data
