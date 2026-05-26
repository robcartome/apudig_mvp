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
    path("customers/", customer_list, name="customer_list"),
    path("customers/new/", customer_create, name="customer_create"),
    path("customers/<uuid:pk>/", customer_detail, name="customer_detail"),
    path("customers/<uuid:pk>/edit/", customer_update, name="customer_update"),
    path("customers/<uuid:pk>/delete/", customer_delete, name="customer_delete"),
    # Contacts
    path("customers/<uuid:customer_pk>/contacts/new/", contact_create, name="contact_create"),
    path("contacts/<uuid:pk>/delete/", contact_delete, name="contact_delete"),
    # Suppliers
    path("suppliers/", supplier_list, name="supplier_list"),
    path("suppliers/new/", supplier_create, name="supplier_create"),
    path("suppliers/<uuid:pk>/edit/", supplier_update, name="supplier_update"),
    path("suppliers/<uuid:pk>/delete/", supplier_delete, name="supplier_delete"),
    # Carriers
    path("carriers/", carrier_list, name="carrier_list"),
    path("carriers/new/", carrier_create, name="carrier_create"),
    path("carriers/<uuid:pk>/edit/", carrier_update, name="carrier_update"),
    path("carriers/<uuid:pk>/delete/", carrier_delete, name="carrier_delete"),
]
