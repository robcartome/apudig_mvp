from decimal import Decimal
from django.db.models import DecimalField, Exists, OuterRef, Prefetch, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from apps.inventory import selectors as inventory_selectors
from apps.inventory.models import ProductPrice, ProductSupplier, StockByWarehouse
from rest_framework.exceptions import ValidationError
import uuid


def filter_catalog_products(products, access, *, brand="", category=""):
    for field, value in (("brand", brand), ("category", category)):
        if value:
            try:
                value = uuid.UUID(str(value))
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValidationError({field: "Usa un identificador UUID válido."}) from exc
            products = products.filter(**{field + "_id": value, field + "__company_id": access.company_id})
    return products


def scoped_stocks(access):
    stocks = StockByWarehouse.objects.filter(product__company_id=access.company_id, warehouse__active=True, warehouse__store__active=True, warehouse__store__company_id=access.company_id)
    if access.store_id:
        stocks = stocks.filter(warehouse__store_id=access.store_id)
    return stocks


def catalog_products(access, search="", include_private=False):
    if access is None or access.company_id is None:
        raise ValueError("Catalog requires an authorized company context")
    products = inventory_selectors.get_products(company_id=access.company_id, active_only=True)
    if search:
        match = Q(name__icontains=search) | Q(sku__icontains=search) | Q(barcode__icontains=search) | Q(model__icontains=search)
        if include_private:
            suppliers = ProductSupplier.objects.filter(product_id=OuterRef("pk"), active=True, supplier__company_id=access.company_id).filter(Q(supplier_code__icontains=search) | Q(supplier_product_name__icontains=search))
            products = products.annotate(catalog_supplier_match=Exists(suppliers))
            match |= Q(catalog_supplier_match=True)
        products = products.filter(match)
    total = scoped_stocks(access).filter(product_id=OuterRef("pk")).values("product_id").annotate(total=Sum("quantity")).values("total")[:1]
    products = products.annotate(stock=Coalesce(Subquery(total, output_field=DecimalField(max_digits=14, decimal_places=3)), Decimal("0")))
    if include_private:
        products = products.prefetch_related(
            Prefetch("prices", queryset=ProductPrice.objects.filter(active=True, price_list__active=True, price_list__company_id=access.company_id).select_related("price_list").order_by("price_list__name"), to_attr="catalog_prices"),
            Prefetch("stocks", queryset=scoped_stocks(access).select_related("warehouse").order_by("warehouse__name"), to_attr="catalog_stocks"),
            Prefetch("supplier_relations", queryset=ProductSupplier.objects.filter(active=True, supplier__company_id=access.company_id).exclude(supplier_code="").order_by("supplier_code"), to_attr="active_supplier_code_relations"),
        )
    return products
