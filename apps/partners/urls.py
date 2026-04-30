from django.urls import path

from .views import (
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

app_name = "partners"

urlpatterns = [
    # Customers
    path("clientes/", customer_list, name="customer_list"),
    path("clientes/nuevo/", customer_create, name="customer_create"),
    path("clientes/<uuid:pk>/", customer_detail, name="customer_detail"),
    path("clientes/<uuid:pk>/editar/", customer_update, name="customer_update"),
    path("clientes/<uuid:pk>/eliminar/", customer_delete, name="customer_delete"),
    # Contacts
    path("clientes/<uuid:customer_pk>/contactos/nuevo/", contact_create, name="contact_create"),
    path("contactos/<uuid:pk>/eliminar/", contact_delete, name="contact_delete"),
    # Suppliers
    path("proveedores/", supplier_list, name="supplier_list"),
    path("proveedores/nuevo/", supplier_create, name="supplier_create"),
    path("proveedores/<uuid:pk>/editar/", supplier_update, name="supplier_update"),
    path("proveedores/<uuid:pk>/eliminar/", supplier_delete, name="supplier_delete"),
    # Carriers
    path("transportistas/", carrier_list, name="carrier_list"),
    path("transportistas/nuevo/", carrier_create, name="carrier_create"),
    path("transportistas/<uuid:pk>/editar/", carrier_update, name="carrier_update"),
    path("transportistas/<uuid:pk>/eliminar/", carrier_delete, name="carrier_delete"),
]
