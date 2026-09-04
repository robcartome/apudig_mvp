from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum

from apps.core.models import AuditLog

from .models import (
    PurchaseDocument, PurchaseDocumentStatus, PurchasePayableInstallment,
    PurchasePaymentStatus, SupplierPayment, SupplierPaymentAllocation,
    SupplierPaymentStatus,
)


MONEY = Decimal("0.01")


def _money(value):
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def ensure_document_installment(document):
    if document.total <= 0 or document.installments.exists():
        return
    PurchasePayableInstallment.objects.create(
        purchase_document=document, sequence=1,
        due_date=document.due_date or document.issue_date, amount=document.total,
    )


@transaction.atomic
def replace_installment_schedule(document_id, *, company_id, schedule):
    document = PurchaseDocument.objects.select_for_update().get(pk=document_id, company_id=company_id)
    if document.document_status != PurchaseDocumentStatus.REGISTERED:
        raise ValueError("Solo se pueden programar cuotas para documentos registrados.")
    if document.installments.filter(payment_allocations__payment__status=SupplierPaymentStatus.REGISTERED).exists():
        raise ValueError("No se pueden modificar las cuotas porque el documento ya tiene pagos.")
    normalized = [
        {"due_date": row["due_date"], "amount": _money(row["amount"])}
        for row in schedule if row.get("due_date") and Decimal(str(row.get("amount") or 0)) > 0
    ]
    if not normalized:
        raise ValueError("Debe existir al menos una cuota.")
    if _money(sum((row["amount"] for row in normalized), Decimal("0"))) != _money(document.total):
        raise ValueError(f"La suma de cuotas debe ser igual al total del documento ({document.total}).")
    document.installments.all().delete()
    PurchasePayableInstallment.objects.bulk_create([
        PurchasePayableInstallment(
            purchase_document=document, sequence=index,
            due_date=row["due_date"], amount=row["amount"],
        ) for index, row in enumerate(normalized, start=1)
    ])
    return document


def installment_paid_amount(installment):
    return installment.payment_allocations.filter(
        payment__status=SupplierPaymentStatus.REGISTERED
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")


def document_payment_summary(document):
    total_paid = SupplierPaymentAllocation.objects.filter(
        installment__purchase_document=document,
        payment__status=SupplierPaymentStatus.REGISTERED,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return {
        "total": document.total,
        "paid": _money(total_paid),
        "balance": _money(max(document.total - total_paid, Decimal("0"))),
    }


def _refresh_document_payment_status(document):
    summary = document_payment_summary(document)
    if summary["paid"] <= 0:
        status = PurchasePaymentStatus.UNPAID
    elif summary["balance"] > 0:
        status = PurchasePaymentStatus.PARTIALLY_PAID
    else:
        status = PurchasePaymentStatus.PAID
    PurchaseDocument.objects.filter(pk=document.pk).update(payment_status=status)
    document.payment_status = status
    return summary


@transaction.atomic
def register_supplier_payment(*, company_id, store, supplier, payment_number, payment_date,
                              currency, exchange_rate, means_of_payment, allocations,
                              created_by=None, reference="", notes=""):
    if str(store.company_id) != str(company_id):
        raise ValueError("La sucursal no pertenece a la empresa activa.")
    if str(supplier.company_id) != str(company_id):
        raise ValueError("El proveedor no pertenece a la empresa activa.")
    if str(means_of_payment.company_id) != str(company_id):
        raise ValueError("El medio de pago no pertenece a la empresa activa.")
    if not allocations:
        raise ValueError("El pago debe aplicarse al menos a una cuota.")

    normalized = []
    seen = set()
    for raw in allocations:
        installment_id = getattr(raw.get("installment"), "pk", raw.get("installment"))
        if installment_id in seen:
            raise ValueError("Una cuota no puede repetirse en el mismo pago.")
        seen.add(installment_id)
        installment = PurchasePayableInstallment.objects.select_for_update().select_related(
            "purchase_document"
        ).get(pk=installment_id)
        document = installment.purchase_document
        if document.document_status != PurchaseDocumentStatus.REGISTERED:
            raise ValueError("Solo se pueden pagar documentos registrados.")
        if str(document.company_id) != str(company_id) or str(document.store_id) != str(store.pk):
            raise ValueError("La cuota no pertenece a la empresa y sucursal activas.")
        if str(document.supplier_id) != str(supplier.pk):
            raise ValueError("Todas las cuotas deben pertenecer al proveedor del pago.")
        if document.currency != currency:
            raise ValueError("La moneda del pago debe coincidir con la del documento.")
        amount = _money(raw.get("amount") or 0)
        pending = _money(installment.amount - installment_paid_amount(installment))
        if amount <= 0:
            raise ValueError("El importe aplicado debe ser mayor que cero.")
        if amount > pending:
            raise ValueError(f"El pago supera el saldo pendiente de la cuota ({pending}).")
        normalized.append((installment, amount))

    total = _money(sum((amount for _, amount in normalized), Decimal("0")))
    payment = SupplierPayment.objects.create(
        company_id=company_id, store=store, supplier=supplier,
        payment_number=payment_number.strip().upper(), payment_date=payment_date,
        currency=currency, exchange_rate=exchange_rate, amount=total,
        means_of_payment=means_of_payment, reference=reference, notes=notes,
        created_by=created_by,
    )
    documents = {}
    for installment, amount in normalized:
        SupplierPaymentAllocation.objects.create(
            payment=payment, installment=installment, amount=amount
        )
        documents[installment.purchase_document_id] = installment.purchase_document
    for document in documents.values():
        _refresh_document_payment_status(document)
    AuditLog.objects.create(
        user=created_by, action="REGISTER", entity="SupplierPayment", entity_id=str(payment.pk),
        meta_data={"supplier_id": str(supplier.pk), "amount": str(total), "currency": currency},
    )
    return payment


@transaction.atomic
def cancel_supplier_payment(payment_id, *, company_id, cancelled_by=None):
    payment = SupplierPayment.objects.select_for_update().prefetch_related(
        "allocations__installment__purchase_document"
    ).get(pk=payment_id, company_id=company_id)
    if payment.status == SupplierPaymentStatus.CANCELLED:
        return payment
    documents = {
        allocation.installment.purchase_document_id: allocation.installment.purchase_document
        for allocation in payment.allocations.all()
    }
    payment.status = SupplierPaymentStatus.CANCELLED
    payment.save(update_fields=("status", "updated_at"))
    for document in documents.values():
        _refresh_document_payment_status(document)
    AuditLog.objects.create(
        user=cancelled_by, action="CANCEL", entity="SupplierPayment", entity_id=str(payment.pk),
        meta_data={"supplier_id": str(payment.supplier_id), "amount": str(payment.amount)},
    )
    return payment
