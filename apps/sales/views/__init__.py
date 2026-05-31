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
    quotation_copy,
    quotation_create,
    quotation_detail,
    quotation_list,
    quotation_reject,
    quotation_update,
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
from .vouchers import (
    voucher_cancel,
    voucher_create,
    voucher_credit,
    voucher_detail,
    voucher_from_ord,
    voucher_issue,
    voucher_list,
    voucher_pdf,
    voucher_void,
)
from .pdf import quotation_pdf

__all__ = [
    # Series / document types
    "series_list", "series_create", "series_update", "series_toggle",
    "doctype_list", "doctype_create", "doctype_update",
    # Quotations
    "quotation_list", "quotation_create", "quotation_detail", "quotation_update",
    "quotation_approve", "quotation_reject", "quotation_cancel", "quotation_copy",
    "quotation_pdf",
    # Orders
    "order_list", "order_create", "order_from_quot", "order_detail", "order_update",
    "order_confirm", "order_cancel", "order_copy", "order_pdf",
    # Vouchers
    "voucher_list", "voucher_create", "voucher_from_ord", "voucher_detail",
    "voucher_issue", "voucher_void", "voucher_cancel", "voucher_credit", "voucher_pdf",
]

