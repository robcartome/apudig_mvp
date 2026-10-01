from django.urls import path

from .views import (
    cash_safe_ledger, cash_session_detail, cash_session_list, receipt_a4, register_create,
    register_list, register_update, sale_workspace, transaction_list,
)


app_name = "pos"

urlpatterns = [
    path("", sale_workspace, name="sale"),
    path("configuracion/", register_list, name="register_list"),
    path("ventas/", transaction_list, name="transaction_list"),
    path("sesiones/", cash_session_list, name="cash_session_list"),
    path("sesiones/<uuid:pk>/", cash_session_detail, name="cash_session_detail"),
    path("caja-fuerte/", cash_safe_ledger, name="cash_safe_ledger"),
    path("configuracion/nueva/", register_create, name="register_create"),
    path("configuracion/<uuid:pk>/editar/", register_update, name="register_update"),
    path("comprobantes/<uuid:transaction_id>/a4/", receipt_a4, name="receipt_a4"),
]
