from django.urls import path

from .views import (
    bank_account_create,
    bank_account_toggle,
    bank_account_update,
    bank_movement_export_xlsx,
    bank_reconciliation_detail,
    bank_reconciliation_list,
    cash_safe_ledger,
    cash_safe_count_list,
    cash_safe_count_detail,
    cash_safe_deposit_list,
    cash_safe_attachment_download,
    cash_safe_export,
    cash_safe_export_xlsx,
    cash_safe_income_create,
    cash_safe_movement_detail,
    treasury_dashboard,
    treasury_fund_list,
)


app_name = "treasury"

urlpatterns = [
    path("", treasury_dashboard, name="dashboard"),
    path("movimientos/reporte.xlsx", bank_movement_export_xlsx, name="bank_movement_export_xlsx"),
    path("fondos/", treasury_fund_list, name="treasury_fund_list"),
    path(
        "ingresos/", treasury_dashboard,
        {"direction": "IN"}, name="bank_income_list",
    ),
    path(
        "egresos/", treasury_dashboard,
        {"direction": "OUT"}, name="bank_expense_list",
    ),
    path("conciliaciones/", bank_reconciliation_list, name="bank_reconciliation_list"),
    path(
        "conciliaciones/<uuid:pk>/",
        bank_reconciliation_detail,
        name="bank_reconciliation_detail",
    ),
    path("configuracion/cuentas/nueva/", bank_account_create, name="bank_account_create"),
    path(
        "configuracion/cuentas/<uuid:pk>/editar/",
        bank_account_update,
        name="bank_account_update",
    ),
    path(
        "configuracion/cuentas/<uuid:pk>/estado/",
        bank_account_toggle,
        name="bank_account_toggle",
    ),
    path("caja-fuerte/", cash_safe_ledger, name="cash_safe_ledger"),
    path("caja-fuerte/ingresos/nuevo/", cash_safe_income_create, name="cash_safe_income_create"),
    path("caja-fuerte/exportar/", cash_safe_export, name="cash_safe_export"),
    path("caja-fuerte/reporte.xlsx", cash_safe_export_xlsx, name="cash_safe_export_xlsx"),
    path("caja-fuerte/movimientos/<uuid:pk>/", cash_safe_movement_detail, name="cash_safe_movement_detail"),
    path("caja-fuerte/adjuntos/<uuid:pk>/", cash_safe_attachment_download, name="cash_safe_attachment_download"),
    path("caja-fuerte/arqueos/", cash_safe_count_list, name="cash_safe_count_list"),
    path("caja-fuerte/arqueos/<uuid:pk>/", cash_safe_count_detail, name="cash_safe_count_detail"),
    path("depositos/", cash_safe_deposit_list, name="cash_safe_deposit_list"),
]
