from django.contrib import admin

from .models import (
    Brand,
    Category,
    Movement,
    MovementDetail,
    PriceList,
    Product,
    ProductPrice,
    StockByWarehouse,
    Unit,
    Warehouse,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "active")
    search_fields = ("code", "name")
    list_filter = ("active",)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "active")
    search_fields = ("name",)
    list_filter = ("active",)


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "active")
    list_filter = ("active",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "price_sale", "price_purchase", "category", "brand", "unit", "active")
    list_filter = ("active", "category", "brand")
    search_fields = ("name", "sku", "barcode")
    ordering = ("name",)


@admin.register(ProductPrice)
class ProductPriceAdmin(admin.ModelAdmin):
    list_display = ("product", "price_list", "amount", "currency", "active")
    list_filter = ("price_list", "active")


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "store", "is_default", "active")
    list_filter = ("store", "active", "is_default")
    search_fields = ("name",)


@admin.register(StockByWarehouse)
class StockByWarehouseAdmin(admin.ModelAdmin):
    list_display = ("product", "warehouse", "quantity")
    list_filter = ("warehouse",)
    search_fields = ("product__sku", "product__name")


class MovementDetailInline(admin.TabularInline):
    model = MovementDetail
    extra = 0
    fields = ("product", "quantity", "unit_price", "physical_quantity")


@admin.register(Movement)
class MovementAdmin(admin.ModelAdmin):
    list_display = ("type", "date", "store", "warehouse", "number", "created_by")
    list_filter = ("type", "store", "warehouse")
    search_fields = ("number", "reason")
    inlines = [MovementDetailInline]
