from django.urls import path

from .views import (
    admin_panel,
    bulk_import,
    bulk_import_errors,
    bulk_import_template,
    brand_create, brand_delete, brand_list, brand_update,
    category_create, category_delete, category_list, category_update,
    customer_search,
    entry_create, exit_create,
    location_search,
    movement_copy, movement_delete, movement_detail, movement_edit, movement_list, movement_confirm,
    price_list_prices,
    pricelist_create, pricelist_del_price, pricelist_detail,
    pricelist_list, pricelist_toggle, pricelist_update,
    pricelist_bulk_import, pricelist_bulk_template,
    pricelist_bulk_import_pl, pricelist_bulk_template_pl,
    price_report,
    product_create, product_delete, product_list, product_update,
    product_quick_create, product_search, product_stock,
    stock_report,
    supplier_search,
    transfer_create, adjustment_create,
    unit_create, unit_delete, unit_list, unit_update,
    warehouse_create, warehouse_delete, warehouse_list, warehouse_update,
    warehouse_location_create, warehouse_location_delete,
    warehouse_location_list, warehouse_location_update,
)

app_name = "inventory"

urlpatterns = [
    path("import/<str:entity>/", bulk_import, name="bulk_import"),
    path("import/<str:entity>/template/", bulk_import_template, name="bulk_import_template"),
    path("import/errors/<str:token>/", bulk_import_errors, name="bulk_import_errors"),

    # API (AJAX)
    path("api/products/",        product_search,       name="api_product_search"),
    path("api/products/stock/",  product_stock,        name="api_product_stock"),
    path("api/products/create/", product_quick_create, name="api_product_create"),
    path("api/price-list/<uuid:pk>/prices/", price_list_prices, name="api_price_list_prices"),
    path("api/suppliers/",       supplier_search,      name="api_supplier_search"),
    path("api/customers/",       customer_search,      name="api_customer_search"),
    path("api/locations/",       location_search,      name="api_location_search"),

    # Stock
    path("stock/", stock_report, name="stock_report"),

    # Movements
    path("movements/", movement_list, name="movement_list"),
    path("movements/<uuid:pk>/", movement_detail, name="movement_detail"),
    path("movements/<uuid:pk>/edit/", movement_edit, name="movement_edit"),
    path("movements/<uuid:pk>/copy/", movement_copy, name="movement_copy"),
    path("movements/<uuid:pk>/confirm/", movement_confirm, name="movement_confirm"),
    path("movements/<uuid:pk>/delete/", movement_delete, name="movement_delete"),
    path("movements/entry/", entry_create, name="entry_create"),
    path("movements/exit/", exit_create, name="exit_create"),
    path("movements/transfer/", transfer_create, name="transfer_create"),
    path("movements/adjustment/", adjustment_create, name="adjustment_create"),

    # Categories
    path("categories/", category_list, name="category_list"),
    path("categories/new/", category_create, name="category_create"),
    path("categories/<uuid:pk>/edit/", category_update, name="category_update"),
    path("categories/<uuid:pk>/delete/", category_delete, name="category_delete"),

    # Brands
    path("brands/", brand_list, name="brand_list"),
    path("brands/new/", brand_create, name="brand_create"),
    path("brands/<uuid:pk>/edit/", brand_update, name="brand_update"),
    path("brands/<uuid:pk>/delete/", brand_delete, name="brand_delete"),

    # Units
    path("units/", unit_list, name="unit_list"),
    path("units/new/", unit_create, name="unit_create"),
    path("units/<uuid:pk>/edit/", unit_update, name="unit_update"),
    path("units/<uuid:pk>/delete/", unit_delete, name="unit_delete"),

    # Warehouses
    path("warehouses/", warehouse_list, name="warehouse_list"),
    path("warehouses/new/", warehouse_create, name="warehouse_create"),
    path("warehouses/<uuid:pk>/edit/", warehouse_update, name="warehouse_update"),
    path("warehouses/<uuid:pk>/delete/", warehouse_delete, name="warehouse_delete"),

    # Warehouse Locations
    path("locations/", warehouse_location_list, name="warehouse_location_list"),
    path("locations/new/", warehouse_location_create, name="warehouse_location_create"),
    path("locations/<uuid:pk>/edit/", warehouse_location_update, name="warehouse_location_update"),
    path("locations/<uuid:pk>/delete/", warehouse_location_delete, name="warehouse_location_delete"),

    # Admin panel
    path("admin/", admin_panel, name="admin_panel"),

    # Products
    path("products/", product_list, name="product_list"),
    path("products/new/", product_create, name="product_create"),
    path("products/<uuid:pk>/edit/", product_update, name="product_update"),
    path("products/<uuid:pk>/delete/", product_delete, name="product_delete"),

    # Price lists
    path("price-lists/", pricelist_list, name="pricelist_list"),
    path("price-lists/new/", pricelist_create, name="pricelist_create"),
    path("price-lists/report/", price_report, name="price_report"),
    path("price-lists/import/", pricelist_bulk_import, name="pricelist_bulk_import"),
    path("price-lists/import/template/", pricelist_bulk_template, name="pricelist_bulk_template"),
    path("price-lists/<uuid:pk>/", pricelist_detail, name="pricelist_detail"),
    path("price-lists/<uuid:pk>/edit/", pricelist_update, name="pricelist_update"),
    path("price-lists/<uuid:pk>/toggle/", pricelist_toggle, name="pricelist_toggle"),
    path("price-lists/<uuid:pk>/price/delete/", pricelist_del_price, name="pricelist_del_price"),
    path("price-lists/<uuid:pk>/import/", pricelist_bulk_import_pl, name="pricelist_bulk_import_pl"),
    path("price-lists/<uuid:pk>/import/template/", pricelist_bulk_template_pl, name="pricelist_bulk_template_pl"),
]
