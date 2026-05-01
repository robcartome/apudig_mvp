from django.urls import path

from .views import (
    doctype_create,
    doctype_list,
    doctype_update,
    series_create,
    series_list,
    series_toggle,
    series_update,
    quotation_approve,
    quotation_cancel,
    quotation_create,
    quotation_detail,
    quotation_list,
    quotation_pdf,
    quotation_reject,
    quotation_update,
)

app_name = "sales"

urlpatterns = [
    # Series documentales
    path("series/", series_list, name="series_list"),
    path("series/nueva/", series_create, name="series_create"),
    path("series/<uuid:pk>/editar/", series_update, name="series_update"),
    path("series/<uuid:pk>/toggle/", series_toggle, name="series_toggle"),
    # Tipos de documento
    path("tipos-documento/", doctype_list, name="doctype_list"),
    path("tipos-documento/nuevo/", doctype_create, name="doctype_create"),
    path("tipos-documento/<uuid:pk>/editar/", doctype_update, name="doctype_update"),
    # Cotizaciones
    path("cotizaciones/", quotation_list, name="quotation_list"),
    path("cotizaciones/nueva/", quotation_create, name="quotation_create"),
    path("cotizaciones/<uuid:pk>/", quotation_detail, name="quotation_detail"),
    path("cotizaciones/<uuid:pk>/editar/", quotation_update, name="quotation_update"),
    path("cotizaciones/<uuid:pk>/aprobar/", quotation_approve, name="quotation_approve"),
    path("cotizaciones/<uuid:pk>/rechazar/", quotation_reject, name="quotation_reject"),
    path("cotizaciones/<uuid:pk>/cancelar/", quotation_cancel, name="quotation_cancel"),
    path("cotizaciones/<uuid:pk>/pdf/", quotation_pdf, name="quotation_pdf"),
]
