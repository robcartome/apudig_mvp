from django.urls import path

from .views import (
    brand_create, brand_delete, brand_list, brand_update,
    category_create, category_delete, category_list, category_update,
    entry_create, exit_create,
    movement_detail, movement_list,
    pricelist_create, pricelist_del_price, pricelist_detail,
    pricelist_list, pricelist_toggle, pricelist_update,
    product_create, product_delete, product_list, product_update,
    stock_report,
    transfer_create,
    unit_create, unit_delete, unit_list, unit_update,
    warehouse_create, warehouse_delete, warehouse_list, warehouse_update,
)

app_name = "inventory"

urlpatterns = [
    # Stock
    path("stock/", stock_report, name="stock_report"),

    # Movements
    path("movimientos/", movement_list, name="movement_list"),
    path("movimientos/<uuid:pk>/", movement_detail, name="movement_detail"),
    path("movimientos/entrada/", entry_create, name="entry_create"),
    path("movimientos/salida/", exit_create, name="exit_create"),
    path("movimientos/transferencia/", transfer_create, name="transfer_create"),

    # Categories
    path("categorias/", category_list, name="category_list"),
    path("categorias/nueva/", category_create, name="category_create"),
    path("categorias/<uuid:pk>/editar/", category_update, name="category_update"),
    path("categorias/<uuid:pk>/eliminar/", category_delete, name="category_delete"),

    # Brands
    path("marcas/", brand_list, name="brand_list"),
    path("marcas/nueva/", brand_create, name="brand_create"),
    path("marcas/<uuid:pk>/editar/", brand_update, name="brand_update"),
    path("marcas/<uuid:pk>/eliminar/", brand_delete, name="brand_delete"),

    # Units
    path("unidades/", unit_list, name="unit_list"),
    path("unidades/nueva/", unit_create, name="unit_create"),
    path("unidades/<uuid:pk>/editar/", unit_update, name="unit_update"),
    path("unidades/<uuid:pk>/eliminar/", unit_delete, name="unit_delete"),

    # Warehouses
    path("almacenes/", warehouse_list, name="warehouse_list"),
    path("almacenes/nuevo/", warehouse_create, name="warehouse_create"),
    path("almacenes/<uuid:pk>/editar/", warehouse_update, name="warehouse_update"),
    path("almacenes/<uuid:pk>/eliminar/", warehouse_delete, name="warehouse_delete"),

    # Products
    path("productos/", product_list, name="product_list"),
    path("productos/nuevo/", product_create, name="product_create"),
    path("productos/<uuid:pk>/editar/", product_update, name="product_update"),
    path("productos/<uuid:pk>/eliminar/", product_delete, name="product_delete"),

    # Price lists
    path("listas-precio/", pricelist_list, name="pricelist_list"),
    path("listas-precio/nueva/", pricelist_create, name="pricelist_create"),
    path("listas-precio/<uuid:pk>/", pricelist_detail, name="pricelist_detail"),
    path("listas-precio/<uuid:pk>/editar/", pricelist_update, name="pricelist_update"),
    path("listas-precio/<uuid:pk>/toggle/", pricelist_toggle, name="pricelist_toggle"),
    path("listas-precio/<uuid:pk>/precio/eliminar/", pricelist_del_price, name="pricelist_del_price"),
]
