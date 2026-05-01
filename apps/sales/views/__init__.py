# sales/views package
from .catalogs import (
    doctype_create,
    doctype_list,
    doctype_update,
    series_create,
    series_list,
    series_toggle,
    series_update,
)
from .quotations import (
    quotation_approve,
    quotation_cancel,
    quotation_create,
    quotation_detail,
    quotation_list,
    quotation_reject,
    quotation_update,
)
from .pdf import quotation_pdf

__all__ = [
    # Series / document types
    "series_list", "series_create", "series_update", "series_toggle",
    "doctype_list", "doctype_create", "doctype_update",
    # Quotations
    "quotation_list", "quotation_create", "quotation_detail", "quotation_update",
    "quotation_approve", "quotation_reject", "quotation_cancel",
    "quotation_pdf",
]

