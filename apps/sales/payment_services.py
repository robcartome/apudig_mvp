"""Sales collections share the POS payment ledger and cash reconciliation."""
from decimal import Decimal

from django.db import transaction

from apps.pos.models import CashSession, PosTransaction, SalesPayment
from apps.pos.services import register_sales_payment
from .models import SalesDocument


COLLECTIBLE_STATUSES = {"ISSUED", "SUNAT_PENDING", "SUNAT_ACCEPTED", "SUNAT_OBSERVED"}
COLLECTIBLE_TYPES = {"NV", "01", "03", "08"}


def is_credit_document(document):
    pos = getattr(document, "pos_transaction", None)
    if pos is not None:
        return pos.payment_condition == PosTransaction.PaymentCondition.CREDIT
    return bool(document.payment_method_id and document.payment_method.is_credit)


def document_payment_summary(document):
    history = getattr(document, "payment_history", None)
    if history is None:
        history = list(document.pos_payments.select_related(
            "means_of_payment", "cash_session__register", "created_by"
        ).order_by("paid_at", "created_at", "pk"))
    payments = [p for p in history if p.status == SalesPayment.Status.REGISTERED]
    paid = sum((p.amount_in_sale_currency for p in payments), Decimal("0.00"))
    collectible = (
        document.status in COLLECTIBLE_STATUSES
        and document.document_type.code in COLLECTIBLE_TYPES
    )
    balance = max(document.total - paid, Decimal("0.00")) if collectible else None
    status = "PAID" if balance == 0 else "PARTIAL" if paid else "PENDING"
    credit = is_credit_document(document)
    pos = getattr(document, "pos_transaction", None)
    return {
        "total": document.total,
        "paid": paid,
        "balance": balance,
        "status": status if collectible else "NOT_APPLICABLE",
        "status_label": {
            "PAID": "Pagado", "PARTIAL": "Parcial", "PENDING": "Pendiente",
        }[status] if collectible else "No aplica",
        "is_credit": credit,
        "last_payment": payments[-1] if payments else None,
        "means": list(dict.fromkeys(p.means_of_payment.name for p in payments)),
        "payments": history,
        "can_collect": bool(
            collectible and balance > 0
            and (pos is None or pos.status == PosTransaction.Status.COMPLETED)
        ),
    }


@transaction.atomic
def register_document_collection(
    *, document_id, company_id, store_id, cash_session_id, means_of_payment_id,
    amount, operation_reference="", idempotency_key, created_by,
):
    # Use the same lock order as collections made from the POS.
    PosTransaction.objects.select_for_update().filter(sales_document_id=document_id).first()
    document = SalesDocument.objects.select_for_update(of=("self",)).select_related(
        "payment_method", "pos_transaction", "document_type"
    ).get(pk=document_id, store_id=store_id, store__company_id=company_id)
    session = CashSession.objects.select_for_update().get(
        pk=cash_session_id, company_id=company_id, store_id=store_id,
        status=CashSession.Status.OPEN, currency=document.currency,
    )
    existing = SalesPayment.objects.filter(
        cash_session=session, idempotency_key=idempotency_key,
    ).first()
    if existing:
        if (existing.sales_document_id != document.pk
                or existing.purpose != SalesPayment.Purpose.CREDIT_COLLECTION
                or existing.status != SalesPayment.Status.REGISTERED):
            raise ValueError("La clave de este cobro ya fue utilizada por otra operación.")
        return existing
    summary = document_payment_summary(document)
    if not summary["can_collect"]:
        raise ValueError("Solo se pueden cobrar ventas emitidas con saldo pendiente.")
    return register_sales_payment(
        sales_document_id=document.pk, cash_session_id=session.pk,
        means_of_payment_id=means_of_payment_id, amount=amount,
        amount_in_sale_currency=amount, operation_reference=operation_reference,
        purpose=SalesPayment.Purpose.CREDIT_COLLECTION,
        idempotency_key=idempotency_key, created_by=created_by,
    )
