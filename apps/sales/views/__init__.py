# sales/views package
from .catalogs import (
    doctype_create,
    doctype_list,
    doctype_update,
    series_create,
    series_list,
    series_toggle,
    series_update,
    api_series_options,
    payment_method_list,
    payment_method_create,
    payment_method_update,
    payment_method_delete,
    api_payment_method_search,
    api_payment_method_create,
    means_of_payment_list,
    means_of_payment_create,
    means_of_payment_update,
    means_of_payment_delete,
    api_means_of_payment_search,
    api_means_of_payment_create,
)
from .quotations import (
    quotation_approve,
    quotation_cancel,
    quotation_copy,
    quotation_create,
    quotation_detail,
    quotation_preview,
    quotation_list,
    quotation_reject,
    quotation_update,
    api_series_next_number,
)
from .orders import (
    order_cancel,
    order_confirm,
    order_copy,
    order_create,
    order_detail,
    order_from_quot,
    order_list,
    order_pdf,
    order_update,
)
from .documents import (
    document_cancel,
    document_create,
    document_copy,
    document_credit,
    document_delete,
    document_detail,
    document_edit,
    document_from_quotation,
    document_from_order,
    document_issue,
    document_list,
    document_preview,
    document_pdf,
    document_void,
)
from .pdf import quotation_pdf
from .pdf import quotation_xlsx

__all__ = [
    # Series / document types
    "series_list", "series_create", "series_update", "series_toggle", "api_series_options",
    "doctype_list", "doctype_create", "doctype_update",
    # Payment conditions / methods
    "payment_condition_list", "payment_condition_create", "payment_condition_update", "payment_condition_delete",
    "api_payment_condition_search", "api_payment_condition_create",
    "payment_method_list", "payment_method_create", "payment_method_update", "payment_method_delete",
    "api_payment_method_search", "api_payment_method_create",
    # Quotations
    "quotation_list", "quotation_create", "quotation_detail", "quotation_update",
    "quotation_approve", "quotation_reject", "quotation_cancel", "quotation_copy",
    "quotation_pdf", "quotation_xlsx", "api_series_next_number", "quotation_preview",
    # Orders
    "order_list", "order_create", "order_from_quot", "order_detail", "order_update",
    "order_confirm", "order_cancel", "order_copy", "order_pdf",
    # Sales documents
    "document_list", "document_create", "document_copy", "document_delete", "document_edit", "document_from_order", "document_from_quotation", "document_detail", "document_preview",
    "document_issue", "document_void", "document_cancel", "document_credit", "document_pdf",
]

