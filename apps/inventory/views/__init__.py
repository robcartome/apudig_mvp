# inventory/views package
from .masters import (
    brand_create, brand_delete, brand_list, brand_update,
    category_create, category_delete, category_list, category_update,
    product_create, product_delete, product_list, product_update,
    unit_create, unit_delete, unit_list, unit_update,
    warehouse_create, warehouse_delete, warehouse_list, warehouse_update,
)

__all__ = [
    "brand_create", "brand_delete", "brand_list", "brand_update",
    "category_create", "category_delete", "category_list", "category_update",
    "product_create", "product_delete", "product_list", "product_update",
    "unit_create", "unit_delete", "unit_list", "unit_update",
    "warehouse_create", "warehouse_delete", "warehouse_list", "warehouse_update",
]
