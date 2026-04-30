# partners/views package
from .partners import (
    carrier_create,
    carrier_delete,
    carrier_list,
    carrier_update,
    contact_create,
    contact_delete,
    customer_create,
    customer_delete,
    customer_detail,
    customer_list,
    customer_update,
    supplier_create,
    supplier_delete,
    supplier_list,
    supplier_update,
)

__all__ = [
    "customer_list", "customer_create", "customer_detail", "customer_update", "customer_delete",
    "contact_create", "contact_delete",
    "supplier_list", "supplier_create", "supplier_update", "supplier_delete",
    "carrier_list", "carrier_create", "carrier_update", "carrier_delete",
]
