# inventory/views package
from .api import (
    customer_search,
    location_search,
    product_quick_create,
    product_search,
    product_stock,
    supplier_search,
)
from .masters import (
    admin_panel,
    brand_create, brand_delete, brand_list, brand_update,
    category_create, category_delete, category_list, category_update,
    product_create, product_delete, product_list, product_update,
    unit_create, unit_delete, unit_list, unit_update,
    warehouse_create, warehouse_delete, warehouse_list, warehouse_update,
    warehouse_location_create, warehouse_location_delete,
    warehouse_location_list, warehouse_location_update,
)
from .operations import (
    adjustment_create,
    entry_create,
    movement_confirm,
    movement_delete,
    movement_edit,
    exit_create,
    movement_detail,
    movement_list,
    stock_report,
    transfer_create,
)
from .pricelists import (
    pricelist_create,
    pricelist_del_price,
    pricelist_detail,
    pricelist_list,
    pricelist_toggle,
    pricelist_update,
)

__all__ = [
    "product_search", "product_stock", "product_quick_create",
    "brand_create", "brand_delete", "brand_list", "brand_update",
    "category_create", "category_delete", "category_list", "category_update",
    "product_create", "product_delete", "product_list", "product_update",
    "unit_create", "unit_delete", "unit_list", "unit_update",
    "warehouse_create", "warehouse_delete", "warehouse_list", "warehouse_update",
    "stock_report",
    "movement_list", "movement_detail",
    "movement_edit", "movement_delete", "movement_confirm",
    "entry_create", "exit_create", "transfer_create", "adjustment_create",
    "pricelist_list", "pricelist_create", "pricelist_detail", "pricelist_update",
    "pricelist_toggle", "pricelist_del_price",
]
