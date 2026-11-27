"""Payment-term rules shared by purchase and expense forms."""


def requires_purchase_due_date(payment_method):
    if payment_method is None:
        return False
    # Cash describes the instrument, not whether the supplier grants credit.
    return payment_method.is_credit or not payment_method.immediate_payment


def purchase_payment_terms_config(form):
    return [
        {"id": str(method.pk), "requires_due_date": requires_purchase_due_date(method)}
        for method in form.fields["payment_method"].queryset
    ]
