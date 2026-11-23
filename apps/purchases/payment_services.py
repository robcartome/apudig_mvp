from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

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
    if document.installments.filter(payment_allocations__payment__status__in=(SupplierPaymentStatus.REGISTERED, SupplierPaymentStatus.PENDING)).exists():
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
    from .notification_providers import schedule_purchase_payable_notification_sync
    schedule_purchase_payable_notification_sync(document)
    return document


def installment_paid_amount(installment):
    return installment.payment_allocations.filter(
        payment__status=SupplierPaymentStatus.REGISTERED
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")


def installment_reserved_amount(installment):
    """Amounts already paid or reserved by a cash request awaiting approval."""
    return installment.payment_allocations.filter(
        payment__status__in=(SupplierPaymentStatus.REGISTERED, SupplierPaymentStatus.PENDING)
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
                              created_by=None, reference="", notes="", bank_account=None,
                              cash_fund=None, advance_amount=None, allow_unlinked=False):
    """Register a payment and its treasury movement atomically.

    ``allow_unlinked`` is reserved for importing historical records which already
    exist outside the treasury ledger; interactive flows always require a source.
    """
    if str(store.company_id) != str(company_id):
        raise ValueError("La sucursal no pertenece a la empresa activa.")
    if str(supplier.company_id) != str(company_id):
        raise ValueError("El proveedor no pertenece a la empresa activa.")
    if str(means_of_payment.company_id) != str(company_id):
        raise ValueError("El medio de pago no pertenece a la empresa activa.")
    if not allocations and not advance_amount:
        raise ValueError("El pago debe aplicarse al menos a una cuota.")
    if allocations and advance_amount:
        raise ValueError("Registre el anticipo sin aplicar a cuotas.")
    if bank_account and cash_fund:
        raise ValueError("Seleccione un único origen de fondos.")
    if not bank_account and not cash_fund and not allow_unlinked:
        raise ValueError("Selecciona un fondo de efectivo o una cuenta bancaria de origen.")
    if (bank_account or cash_fund) and payment_date > timezone.now():
        raise ValueError("La fecha de pago no puede estar en el futuro.")
    if means_of_payment.requires_reference and not (reference or "").strip():
        raise ValueError("El medio de pago requiere una referencia de operación.")
    if cash_fund and means_of_payment.kind != "CASH":
        raise ValueError("El fondo de efectivo requiere un medio de pago en efectivo.")
    if bank_account and means_of_payment.kind == "CASH":
        raise ValueError("Un pago en efectivo debe salir de un fondo de efectivo.")
    if bank_account and (str(bank_account.company_id) != str(company_id) or bank_account.currency != currency):
        raise ValueError("La cuenta bancaria debe pertenecer a la empresa y usar la moneda del pago.")

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
        pending = _money(installment.amount - installment_reserved_amount(installment))
        if amount <= 0:
            raise ValueError("El importe aplicado debe ser mayor que cero.")
        if amount > pending:
            raise ValueError(f"El pago supera el saldo pendiente de la cuota ({pending}).")
        normalized.append((installment, amount))

    total = _money(advance_amount if advance_amount is not None else sum((amount for _, amount in normalized), Decimal("0")))
    if total <= 0:
        raise ValueError("El importe debe ser mayor que cero.")
    payment = SupplierPayment.objects.create(
        company_id=company_id, store=store, supplier=supplier,
        payment_number=payment_number.strip().upper(), payment_date=payment_date,
        currency=currency, exchange_rate=exchange_rate, amount=total,
        means_of_payment=means_of_payment, reference=reference, notes=notes,
        status=SupplierPaymentStatus.PENDING if cash_fund else SupplierPaymentStatus.REGISTERED,
        created_by=created_by,
    )
    documents = {}
    for installment, amount in normalized:
        SupplierPaymentAllocation.objects.create(
            payment=payment, installment=installment, amount=amount
        )
        documents[installment.purchase_document_id] = installment.purchase_document
    if bank_account:
        from apps.treasury.models import BankMovement
        from apps.treasury.services import register_linked_collection
        payment.bank_movement = register_linked_collection(
            account=bank_account, amount=total,
            operation_date=timezone.localtime(payment_date).date(),
            reference=reference, description=f"Pago a {supplier.name} · {payment.payment_number}",
            source_type="SUPPLIER_PAYMENT", source_id=payment.pk, user=created_by,
            direction=BankMovement.Direction.OUT,
        )
        payment.save(update_fields=("bank_movement", "updated_at"))
    elif cash_fund:
        from apps.treasury.models import CashSafeMovement
        from apps.treasury.services import register_cash_safe_withdrawal
        payment.cash_movement = register_cash_safe_withdrawal(
            company_id=company_id, store_id=store.pk, fund=cash_fund,
            movement_type=CashSafeMovement.MovementType.CASH_PAYMENT,
            amount=total, currency=currency, recipient_name=supplier.name,
            supplier=supplier, purchase_document=next(iter(documents.values())) if len(documents) == 1 else None,
            reference=reference, notes=f"Pago {payment.payment_number}. {notes}"[:500], user=created_by,
        )
        payment.save(update_fields=("cash_movement", "updated_at"))
    for document in documents.values():
        _refresh_document_payment_status(document)
        from .notification_providers import schedule_purchase_payable_notification_sync
        schedule_purchase_payable_notification_sync(document)
    AuditLog.objects.create(
        user=created_by, action="REGISTER", entity="SupplierPayment", entity_id=str(payment.pk),
        meta_data={"supplier_id": str(supplier.pk), "amount": str(total), "currency": currency},
    )
    return payment


@transaction.atomic
def apply_supplier_advance(*, payment_id, document_id, company_id, store, amount, user=None):
    """Allocate existing money to a later invoice without another treasury movement."""
    payment = SupplierPayment.objects.select_for_update().get(
        pk=payment_id, company_id=company_id, store=store,
        status=SupplierPaymentStatus.REGISTERED,
    )
    document = PurchaseDocument.objects.select_for_update().get(
        pk=document_id, company_id=company_id, store=store,
        document_status=PurchaseDocumentStatus.REGISTERED,
    )
    if payment.supplier_id != document.supplier_id or payment.currency != document.currency:
        raise ValueError("El anticipo debe corresponder al proveedor y moneda del documento.")
    amount = _money(amount)
    allocated = payment.allocations.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    if amount <= 0 or amount > payment.amount - allocated:
        raise ValueError("El importe supera el saldo disponible del anticipo.")
    installments = list(document.installments.select_for_update().order_by("due_date", "sequence"))
    available = sum((item.amount - installment_reserved_amount(item) for item in installments), Decimal("0"))
    if amount > available:
        raise ValueError("El importe supera el saldo disponible de las cuotas.")
    remaining = amount
    for installment in installments:
        applied = min(remaining, installment.amount - installment_reserved_amount(installment))
        if applied > 0:
            allocation, created = SupplierPaymentAllocation.objects.get_or_create(
                payment=payment, installment=installment, defaults={"amount": applied},
            )
            if not created:
                allocation.amount += applied
                allocation.save(update_fields=("amount",))
            remaining -= applied
        if remaining <= 0:
            break
    _refresh_document_payment_status(document)
    from .notification_providers import schedule_purchase_payable_notification_sync
    schedule_purchase_payable_notification_sync(document)
    AuditLog.objects.create(user=user, action="ALLOCATE", entity="SupplierPayment", entity_id=str(payment.pk),
                            meta_data={"document_id": str(document.pk), "amount": str(amount)})
    return payment


def settle_cash_supplier_payment(movement, *, approved):
    """Keep the payable in step with the cash approval or rejection."""
    payment = SupplierPayment.objects.select_for_update().filter(cash_movement=movement).first()
    if not payment:
        return
    if payment.status != SupplierPaymentStatus.PENDING:
        raise ValueError("El pago vinculado ya fue atendido.")
    payment.status = SupplierPaymentStatus.REGISTERED if approved else SupplierPaymentStatus.CANCELLED
    payment.save(update_fields=("status", "updated_at"))
    for allocation in payment.allocations.select_related("installment__purchase_document"):
        document = allocation.installment.purchase_document
        _refresh_document_payment_status(document)
        from .notification_providers import schedule_purchase_payable_notification_sync
        schedule_purchase_payable_notification_sync(document)


@transaction.atomic
def update_supplier_payment_details(
    payment_id, *, company_id, store, payment_date, means_of_payment,
    reference="", notes="", updated_by=None,
):
    """Update operational payment data without rewriting financial allocations."""
    payment = SupplierPayment.objects.select_for_update().get(
        pk=payment_id, company_id=company_id, store_id=store.pk
    )
    if payment.status != SupplierPaymentStatus.REGISTERED:
        raise ValueError("Solo se pueden modificar pagos registrados.")
    if payment.bank_movement_id or payment.cash_movement_id:
        raise ValueError("Para corregir un pago vinculado a tesorería, anúlalo y registra uno nuevo.")
    if str(store.company_id) != str(company_id):
        raise ValueError("La sucursal no pertenece a la empresa activa.")
    if str(means_of_payment.company_id) != str(company_id):
        raise ValueError("El medio de pago no pertenece a la empresa activa.")

    previous = {
        "payment_date": payment.payment_date.isoformat(),
        "means_of_payment_id": str(payment.means_of_payment_id),
        "reference": payment.reference,
        "notes": payment.notes,
    }
    payment.payment_date = payment_date
    payment.means_of_payment = means_of_payment
    payment.reference = (reference or "").strip()
    payment.notes = (notes or "").strip()
    payment.save(update_fields=(
        "payment_date", "means_of_payment", "reference", "notes", "updated_at"
    ))
    AuditLog.objects.create(
        user=updated_by,
        action="UPDATE",
        entity="SupplierPayment",
        entity_id=str(payment.pk),
        meta_data={
            "previous": previous,
            "current": {
                "payment_date": payment.payment_date.isoformat(),
                "means_of_payment_id": str(payment.means_of_payment_id),
                "reference": payment.reference,
                "notes": payment.notes,
            },
        },
    )
    return payment


@transaction.atomic
def cancel_supplier_payment(payment_id, *, company_id, cancelled_by=None):
    payment = SupplierPayment.objects.select_for_update().prefetch_related(
        "allocations__installment__purchase_document"
    ).get(pk=payment_id, company_id=company_id)
    if payment.status == SupplierPaymentStatus.CANCELLED:
        return payment
    if payment.status == SupplierPaymentStatus.PENDING:
        raise ValueError("Rechaza la solicitud de efectivo desde Tesorería.")
    if payment.bank_movement_id or payment.cash_movement_id:
        from apps.treasury.services import reverse_bank_movement, reverse_cash_safe_movement
        reason = f"Anulación del pago {payment.payment_number}"
        if payment.bank_movement_id:
            reverse_bank_movement(movement_id=payment.bank_movement_id, company_id=company_id,
                                  reason=reason, user=cancelled_by, from_supplier_payment=True)
        else:
            reverse_cash_safe_movement(movement_id=payment.cash_movement_id, company_id=company_id,
                                       store_id=payment.store_id, reason=reason, user=cancelled_by,
                                       from_supplier_payment=True)
    documents = {
        allocation.installment.purchase_document_id: allocation.installment.purchase_document
        for allocation in payment.allocations.all()
    }
    payment.status = SupplierPaymentStatus.CANCELLED
    payment.save(update_fields=("status", "updated_at"))
    for document in documents.values():
        _refresh_document_payment_status(document)
        from .notification_providers import schedule_purchase_payable_notification_sync
        schedule_purchase_payable_notification_sync(document)
    AuditLog.objects.create(
        user=cancelled_by, action="CANCEL", entity="SupplierPayment", entity_id=str(payment.pk),
        meta_data={"supplier_id": str(payment.supplier_id), "amount": str(payment.amount)},
    )
    return payment
