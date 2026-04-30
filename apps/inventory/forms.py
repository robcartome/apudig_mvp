from django import forms

from .models import Brand, Category, Movement, MovementDetail, Product, Unit, Warehouse


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ("code", "name", "active")


class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = ("name", "active")


class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ("code", "name")


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = (
            "name", "sku", "barcode", "description", "model",
            "price_purchase", "price_sale",
            "category", "brand", "unit", "active",
        )


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ("store", "name", "description", "active", "is_default")
