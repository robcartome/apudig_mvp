from django.urls import path

from . import views


app_name = "purchases"

urlpatterns = [
    path("expense-categories/new/", views.purchase_category_create, name="expense_category_create"),
    path("expense-categories/<uuid:pk>/edit/", views.purchase_category_update, name="expense_category_update"),
    path("expense-categories/<uuid:pk>/toggle/", views.purchase_category_toggle, name="expense_category_toggle"),
    path("expense-categories/<uuid:pk>/delete/", views.purchase_category_delete, name="expense_category_delete"),
    path("orders/", views.purchase_order_list, name="order_list"),
    path("orders/new/", views.purchase_order_create, name="order_create"),
    path("orders/<uuid:pk>/", views.purchase_order_detail, name="order_detail"),
    path("orders/<uuid:pk>/edit/", views.purchase_order_edit, name="order_edit"),
    path("orders/<uuid:pk>/approve/", views.purchase_order_approve, name="order_approve"),
    path("orders/<uuid:pk>/cancel/", views.purchase_order_cancel, name="order_cancel"),
    path("orders/<uuid:order_pk>/receipts/new/", views.purchase_receipt_create, name="receipt_create"),
    path("receipts/<uuid:pk>/cancel/", views.purchase_receipt_cancel, name="receipt_cancel"),
    path("reports/price-history/", views.purchase_price_history, name="price_history"),
    path("reports/analytics/", views.purchase_analytics, name="analytics"),
    path("accounts-payable/", views.accounts_payable_list, name="accounts_payable_list"),
    path("documents/", views.purchase_document_list, name="document_list"),
    path("documents/new/", views.purchase_document_create, name="document_create"),
    path("expenses/new/", views.purchase_expense_create, name="expense_create"),
    path("expenses/<uuid:pk>/edit/", views.purchase_expense_edit, name="expense_edit"),
    path("documents/<uuid:pk>/", views.purchase_document_detail, name="document_detail"),
    path("documents/<uuid:pk>/preview/", views.purchase_document_preview, name="document_preview"),
    path("documents/<uuid:pk>/edit/", views.purchase_document_edit, name="document_edit"),
    path("documents/<uuid:pk>/register/", views.purchase_document_register, name="document_register"),
    path("documents/<uuid:pk>/cancel/", views.purchase_document_cancel, name="document_cancel"),
    path("documents/<uuid:pk>/delete/", views.purchase_document_delete, name="document_delete"),
    path("documents/<uuid:document_pk>/payments/new/", views.supplier_payment_create, name="payment_create"),
    path("documents/<uuid:document_pk>/installments/", views.purchase_installment_schedule, name="installment_schedule"),
    path("documents/<uuid:document_pk>/landed-costs/new/", views.purchase_landed_cost_create, name="landed_cost_create"),
    path("landed-costs/<uuid:pk>/cancel/", views.purchase_landed_cost_cancel, name="landed_cost_cancel"),
    path("payments/<uuid:pk>/cancel/", views.supplier_payment_cancel, name="payment_cancel"),
]
