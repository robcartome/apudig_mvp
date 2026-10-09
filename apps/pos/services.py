from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.models import AuditLog
from apps.core.currency import currency_symbol
from apps.inventory.models import MovementOrigin, PriceList, Product, ProductPrice, ProductUnit, Unit, Warehouse
from apps.inventory.pricing import split_final_price, tax_rate_for_company
from apps.inventory.services import confirm_movement, register_entry
from apps.partners.models import Customer, DocumentType
from apps.sales.models import DocumentSeries, MeansOfPayment, PaymentMethod, SalesDocument
from apps.sales.services import (
    cancel_sales_document,
    create_credit_note,
    create_debit_note,
    create_sales_document_draft,
    issue_sales_document,
    update_sales_document_draft,
    void_sales_document,
)

from .models import (
    CashDenominationCount,
    CashMovement,
    CashSafeMovement,
    CashSession,
    CashTenderDeclaration,
    PosRegister,
    PosRefundPayment,
    PosReturn,
    PosReturnLine,
    PosTransaction,
    SalesDocumentSource,
    SalesPayment,
)
from .selectors import calculate_cash_session_totals


MONEY_QUANTUM = Decimal("0.01")
POS_MANUAL_PRODUCT_SKU = "VARIOS-POS"


class PosDomainError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _money(value, field_name="importe") -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(MONEY_QUANTUM)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PosDomainError("INVALID_AMOUNT", f"El {field_name} no es valido.") from exc
    if not amount.is_finite():
        raise PosDomainError("INVALID_AMOUNT", f"El {field_name} no es valido.")
    return amount


def _manual_pos_product(company_id, unit_id) -> Product:
    """Devuelve el único artículo técnico usado por líneas libres del POS."""
    unit = Unit.objects.filter(pk=unit_id).first()
    if unit is None:
        raise PosDomainError("INVALID_PRODUCT_UNIT", "Seleccione una unidad válida.")
    product, created = Product.objects.get_or_create(
        company_id=company_id,
        sku=POS_MANUAL_PRODUCT_SKU,
        defaults={
            "name": "Línea libre POS",
            "description": "Artículo técnico para conceptos manuales no inventariables.",
            "unit": unit,
            "price_sale": Decimal("0.00"),
            "tax_affectation": "10",
            "tracks_inventory": False,
            "active": True,
        },
    )
    if created:
        AuditLog.objects.create(
            action="CREATE",
            entity="Product",
            entity_id=str(product.pk),
            meta_data={
                "source": "POS_MANUAL_LINE",
                "company_id": str(company_id),
                "sku": POS_MANUAL_PRODUCT_SKU,
            },
        )
    update_fields = []
    if product.tracks_inventory:
        product.tracks_inventory = False
        update_fields.append("tracks_inventory")
    if not product.active:
        product.active = True
        update_fields.append("active")
    if update_fields:
        product.save(update_fields=(*update_fields, "updated_at"))
    ProductUnit.objects.get_or_create(
        product=product,
        unit=unit,
        defaults={
            "conversion_factor": 1,
            "is_default_sale": created or product.unit_id == unit.pk,
            "is_default_purchase": created or product.unit_id == unit.pk,
            "active": True,
        },
    )
    return product


def _audit(entity, action: str, user=None, **metadata) -> None:
    AuditLog.objects.create(
        user=user,
        action=action,
        entity=entity.__class__.__name__,
        entity_id=str(entity.pk),
        meta_data=metadata,
    )


def _create_denomination_counts(session, phase, denominations) -> Decimal:
    total = Decimal("0.00")
    seen = set()
    for item in denominations or []:
        denomination = _money(item["denomination"], "valor de denominacion")
        try:
            quantity = int(item["quantity"])
        except (TypeError, ValueError) as exc:
            raise PosDomainError(
                "INVALID_DENOMINATION", "La cantidad de denominaciones no es valida."
            ) from exc
        if denomination <= 0 or quantity < 0:
            raise PosDomainError(
                "INVALID_DENOMINATION", "Las denominaciones deben ser positivas."
            )
        if denomination in seen:
            raise PosDomainError(
                "DUPLICATE_DENOMINATION", "Una denominacion no puede repetirse."
            )
        seen.add(denomination)
        line_total = (denomination * quantity).quantize(MONEY_QUANTUM)
        count = CashDenominationCount(
            cash_session=session,
            phase=phase,
            denomination=denomination,
            quantity=quantity,
            total=line_total,
        )
        count.full_clean()
        count.save()
        total += line_total
    return total.quantize(MONEY_QUANTUM)


@transaction.atomic
def open_cash_session(
    *, register_id, opened_by, opening_total=0, denominations=None, note="", currency="PEN"
) -> CashSession:
    register = (
        PosRegister.objects.select_for_update()
        .select_related("company", "store")
        .get(pk=register_id)
    )
    if not register.active:
        raise PosDomainError("POS_REGISTER_INACTIVE", "La caja seleccionada esta inactiva.")
    if CashSession.objects.filter(register=register, status=CashSession.Status.OPEN).exists():
        raise PosDomainError("CASH_SESSION_ALREADY_OPEN", "La caja ya tiene una sesion abierta.")
    currency = (currency or "PEN").upper()
    if currency not in {"PEN", "USD"}:
        raise PosDomainError("INVALID_CASH_SESSION_CURRENCY", "La moneda debe ser S/. o $.")

    opening_total = _money(opening_total, "fondo inicial")
    if opening_total < 0:
        raise PosDomainError("INVALID_OPENING_TOTAL", "El fondo inicial no puede ser negativo.")

    register.current_session_number += 1
    register.save(update_fields=("current_session_number", "updated_at"))
    session = CashSession(
        register=register,
        session_number=register.current_session_number,
        currency=currency,
        company=register.company,
        store=register.store,
        opened_by=opened_by,
        opening_total=opening_total,
        opening_note=(note or "").strip(),
    )
    session.full_clean()
    session.save()

    if denominations is not None:
        counted = _create_denomination_counts(
            session, CashDenominationCount.Phase.OPENING, denominations
        )
        if counted != opening_total:
            raise PosDomainError(
                "OPENING_COUNT_MISMATCH",
                "El conteo por denominaciones no coincide con el fondo inicial.",
            )

    _audit(
        session, "OPEN", opened_by,
        register_id=str(register.pk), opening_total=str(opening_total),
        session_number=session.session_number, currency=currency,
    )
    return session


@transaction.atomic
def register_cash_movement(
    *, cash_session_id, movement_type, amount, description, created_by,
    reason_code="", authorized_by=None, means_of_payment_id=None, operation_reference="",
) -> CashMovement:
    session = CashSession.objects.select_for_update().get(pk=cash_session_id)
    if session.status != CashSession.Status.OPEN:
        raise PosDomainError("CASH_SESSION_CLOSED", "La sesion de caja esta cerrada.")
    amount = _money(amount)
    if amount <= 0:
        raise PosDomainError("INVALID_AMOUNT", "El importe debe ser mayor que cero.")
    if movement_type not in CashMovement.MovementType.values:
        raise PosDomainError("INVALID_CASH_MOVEMENT", "El tipo de movimiento no es valido.")
    if not (description or "").strip():
        raise PosDomainError("CASH_MOVEMENT_REASON_REQUIRED", "Debe indicar el motivo del movimiento.")
    means_of_payment = None
    if means_of_payment_id:
        means_of_payment = MeansOfPayment.objects.filter(
            pk=means_of_payment_id, company_id=session.company_id, active=True,
        ).first()
        if means_of_payment is None:
            raise PosDomainError("INVALID_MEANS_OF_PAYMENT", "El medio de pago no es valido.")
    if (
        movement_type in (CashMovement.MovementType.WITHDRAWAL, CashMovement.MovementType.DEPOSIT)
        and authorized_by is None
    ):
        raise PosDomainError(
            "CASH_MOVEMENT_AUTHORIZATION_REQUIRED",
            "Los retiros y depositos requieren autorizacion de un responsable.",
        )

    movement = CashMovement(
        cash_session=session,
        movement_type=movement_type,
        amount=amount,
        means_of_payment=means_of_payment,
        operation_reference=(operation_reference or "").strip(),
        reason_code=(reason_code or "").strip(),
        description=description.strip(),
        created_by=created_by,
        authorized_by=authorized_by,
    )
    movement.full_clean()
    movement.save()
    movement.drawer_cash_after = calculate_cash_session_totals(session)["expected_cash_total"]
    _audit(
        movement, "REGISTER", created_by,
        cash_session_id=str(session.pk), movement_type=movement_type, amount=str(amount),
        means_of_payment_id=(str(means_of_payment.pk) if means_of_payment else None),
        operation_reference=movement.operation_reference,
        reason_code=movement.reason_code, description=movement.description,
        authorized_by_id=(str(authorized_by.pk) if authorized_by else None),
        drawer_cash_after=str(movement.drawer_cash_after),
    )
    return movement


@transaction.atomic
def start_pos_transaction(
    *, cash_session_id, sales_document_id, idempotency_key, cashier,
    device_identifier="", payment_condition=PosTransaction.PaymentCondition.CASH,
) -> tuple[PosTransaction, bool]:
    session = (
        CashSession.objects.select_for_update(of=("self",))
        .select_related("register", "company", "store")
        .get(pk=cash_session_id)
    )
    if session.status != CashSession.Status.OPEN:
        raise PosDomainError("CASH_SESSION_REQUIRED", "Se requiere una sesion de caja abierta.")

    existing = PosTransaction.objects.filter(
        company=session.company,
        register=session.register,
        idempotency_key=idempotency_key,
    ).first()
    if existing:
        if str(existing.sales_document_id) != str(sales_document_id):
            raise PosDomainError(
                "IDEMPOTENCY_CONFLICT",
                "La clave de idempotencia ya fue utilizada por otra venta.",
            )
        return existing, False

    document = SalesDocument.objects.select_for_update(of=("self",)).select_related(
        "store__company", "document_type"
    ).get(pk=sales_document_id)
    if document.store_id != session.store_id:
        raise PosDomainError("STORE_MISMATCH", "El documento no pertenece a la sucursal de la caja.")
    if document.currency != session.currency:
        raise PosDomainError(
            "CASH_SESSION_CURRENCY_MISMATCH",
            "La moneda de la venta debe coincidir con la moneda de la sesion de caja.",
        )
    if hasattr(document, "pos_transaction"):
        raise PosDomainError("DOCUMENT_ALREADY_IN_POS", "El documento ya pertenece a una venta POS.")

    register = PosRegister.objects.select_for_update().get(pk=session.register_id)
    register.current_ticket_number += 1
    register.save(update_fields=("current_ticket_number", "updated_at"))
    ticket_code = f"{register.ticket_series}-{register.current_ticket_number:08d}"
    billing_status = (
        PosTransaction.BillingStatus.INVOICED
        if document.document_type.code in ("01", "03")
        else PosTransaction.BillingStatus.NOT_REQUESTED
    )
    pos_transaction = PosTransaction(
        company=session.company,
        store=session.store,
        register=register,
        cash_session=session,
        sales_document=document,
        cashier=cashier,
        status=PosTransaction.Status.PROCESSING,
        billing_status=billing_status,
        payment_condition=payment_condition,
        idempotency_key=idempotency_key,
        ticket_number=register.current_ticket_number,
        ticket_code=ticket_code,
        device_identifier=(device_identifier or "").strip(),
    )
    pos_transaction.full_clean()
    pos_transaction.save()
    _audit(
        pos_transaction, "START", cashier,
        cash_session_id=str(session.pk),
        sales_document_id=str(document.pk),
        payment_condition=payment_condition,
        due_date=str(document.due_date) if document.due_date else None,
    )
    return pos_transaction, True


@transaction.atomic
def complete_pos_transaction(
    pos_transaction_id, completed_by=None, allow_outstanding=False,
) -> PosTransaction:
    pos_transaction = PosTransaction.objects.select_for_update().get(pk=pos_transaction_id)
    if pos_transaction.status == PosTransaction.Status.COMPLETED:
        return pos_transaction
    if pos_transaction.status != PosTransaction.Status.PROCESSING:
        raise PosDomainError(
            "INVALID_POS_TRANSACTION_STATE", "Solo una transaccion en proceso puede completarse."
        )
    paid = (
        pos_transaction.sales_document.pos_payments.filter(
            status=SalesPayment.Status.REGISTERED,
            cash_session=pos_transaction.cash_session,
        )
        .aggregate(total=Sum("amount_in_sale_currency"))["total"]
        or Decimal("0.00")
    )
    paid = paid.quantize(MONEY_QUANTUM)
    total = pos_transaction.sales_document.total.quantize(MONEY_QUANTUM)
    if not allow_outstanding and paid != total:
        raise PosDomainError("PAYMENT_MISMATCH", "Los pagos no cuadran con el total de la venta.")
    if paid > total:
        raise PosDomainError("PAYMENT_EXCEEDS_TOTAL", "Los pagos superan el total de la venta.")
    if paid == total:
        pos_transaction.payment_status = PosTransaction.PaymentStatus.PAID
    elif paid > 0:
        pos_transaction.payment_status = PosTransaction.PaymentStatus.PARTIAL
    else:
        pos_transaction.payment_status = PosTransaction.PaymentStatus.PENDING
    pos_transaction.status = PosTransaction.Status.COMPLETED
    pos_transaction.completed_at = timezone.now()
    pos_transaction.failure_code = ""
    pos_transaction.failure_message = ""
    pos_transaction.full_clean()
    pos_transaction.save(
        update_fields=(
            "status", "payment_status", "completed_at", "failure_code",
            "failure_message", "updated_at"
        )
    )
    _audit(
        pos_transaction,
        "COMPLETE",
        completed_by or pos_transaction.cashier,
        paid_amount=str(paid),
        outstanding_amount=str((total - paid).quantize(MONEY_QUANTUM)),
        payment_status=pos_transaction.payment_status,
    )
    return pos_transaction


@transaction.atomic
def cancel_pos_draft(*, pos_transaction_id, cancelled_by) -> PosTransaction:
    pos_transaction = PosTransaction.objects.select_for_update().select_related(
        "sales_document", "cash_session"
    ).get(pk=pos_transaction_id)
    if pos_transaction.status != PosTransaction.Status.DRAFT:
        raise PosDomainError("NOT_A_POS_DRAFT", "Solo se puede descartar una venta POS en borrador.")
    if pos_transaction.sales_document.pos_payments.filter(
        status=SalesPayment.Status.REGISTERED
    ).exists():
        raise PosDomainError("DRAFT_HAS_PAYMENTS", "El borrador tiene pagos registrados.")
    cancel_sales_document(pos_transaction.sales_document_id, cancelled_by=cancelled_by)
    pos_transaction.status = PosTransaction.Status.CANCELLED
    pos_transaction.completed_at = timezone.now()
    pos_transaction.save(update_fields=("status", "completed_at", "updated_at"))
    _audit(pos_transaction, "CANCEL_DRAFT", cancelled_by)
    return pos_transaction


@transaction.atomic
def void_pos_transaction(*, pos_transaction_id, reason, voided_by) -> PosTransaction:
    pos_transaction = (
        PosTransaction.objects.select_for_update(of=("self",))
        .select_related("cash_session", "sales_document__document_type")
        .get(pk=pos_transaction_id)
    )
    if pos_transaction.status != PosTransaction.Status.COMPLETED:
        raise PosDomainError(
            "INVALID_POS_TRANSACTION_STATE",
            "Solo una venta POS completada puede anularse.",
        )
    if pos_transaction.cash_session.status != CashSession.Status.OPEN:
        raise PosDomainError(
            "CASH_SESSION_CLOSED",
            "Una venta de una caja cerrada debe procesarse mediante devolucion.",
        )
    if pos_transaction.sales_document.document_type.code != "NV":
        raise PosDomainError(
            "FISCAL_VOID_REQUIRED",
            "La anulacion de boletas y facturas requiere el flujo fiscal correspondiente.",
        )
    if pos_transaction.sales_document.target_document_links.exists():
        raise PosDomainError(
            "POS_TICKET_ALREADY_INVOICED",
            "No se puede anular un ticket que ya fue incluido en una factura.",
        )
    if not (reason or "").strip():
        raise PosDomainError("VOID_REASON_REQUIRED", "Debe indicar el motivo de anulacion.")

    try:
        void_sales_document(
            pos_transaction.sales_document_id,
            reason=reason.strip(),
            voided_by=voided_by,
        )
    except ValueError as exc:
        raise PosDomainError("INVALID_POS_VOID", str(exc)) from exc
    pos_transaction.sales_document.pos_payments.filter(
        status=SalesPayment.Status.REGISTERED
    ).update(status=SalesPayment.Status.CANCELLED, updated_at=timezone.now())
    pos_transaction.status = PosTransaction.Status.CANCELLED
    pos_transaction.billing_status = PosTransaction.BillingStatus.NOT_REQUESTED
    pos_transaction.save(update_fields=("status", "billing_status", "updated_at"))
    _audit(pos_transaction, "VOID", voided_by, reason=reason.strip())
    return pos_transaction


def _fiscal_document_for_transaction(pos_transaction: PosTransaction) -> SalesDocument:
    document = pos_transaction.sales_document
    if document.document_type.code == "NV":
        link = document.target_document_links.select_related(
            "target_document__document_type"
        ).first()
        if link is not None:
            return link.target_document
    return document


@transaction.atomic
def refund_pos_transaction(
    *, pos_transaction_id, cash_session_id, idempotency_key, line_items,
    refund_means_of_payment_id, reason, created_by, credit_note_series_id=None,
    reason_code="01", operation_reference="",
) -> tuple[PosReturn, bool]:
    """Registra una devolución parcial/total con stock, caja y nota fiscal atómicos."""
    cash_session = CashSession.objects.select_for_update().select_related(
        "register", "company", "store"
    ).get(pk=cash_session_id)
    if cash_session.status != CashSession.Status.OPEN:
        raise PosDomainError("CASH_SESSION_CLOSED", "La devolución requiere una caja abierta.")

    existing = PosReturn.objects.filter(
        company_id=cash_session.company_id,
        register_id=cash_session.register_id,
        idempotency_key=idempotency_key,
    ).first()
    if existing is not None:
        return existing, False

    pos_transaction = PosTransaction.objects.select_for_update(of=("self",)).select_related(
        "sales_document__document_type", "sales_document__warehouse"
    ).get(pk=pos_transaction_id)
    if (
        pos_transaction.company_id != cash_session.company_id
        or pos_transaction.store_id != cash_session.store_id
    ):
        raise PosDomainError("RETURN_CONTEXT_MISMATCH", "La venta pertenece a otra empresa o sucursal.")
    if pos_transaction.status != PosTransaction.Status.COMPLETED:
        raise PosDomainError("INVALID_POS_TRANSACTION_STATE", "Solo se puede devolver una venta completada.")
    if pos_transaction.payment_status != PosTransaction.PaymentStatus.PAID:
        raise PosDomainError(
            "RETURN_REQUIRES_PAID_SALE",
            "La devolución básica requiere una venta totalmente pagada.",
        )
    if not (reason or "").strip():
        raise PosDomainError("RETURN_REASON_REQUIRED", "Debe indicar el motivo de devolución.")
    if not line_items:
        raise PosDomainError("RETURN_LINES_REQUIRED", "Seleccione al menos un producto.")

    source_document = pos_transaction.sales_document
    if source_document.currency != cash_session.currency:
        raise PosDomainError(
            "CASH_SESSION_CURRENCY_MISMATCH",
            "La devolucion debe registrarse en una sesion con la misma moneda de la venta.",
        )
    requested = {}
    for item in line_items:
        line_id = str(item["line_id"])
        if line_id in requested:
            raise PosDomainError("DUPLICATE_RETURN_LINE", "Una línea no puede repetirse.")
        quantity = Decimal(str(item["quantity"]))
        if not quantity.is_finite() or quantity <= 0:
            raise PosDomainError("INVALID_RETURN_QUANTITY", "La cantidad devuelta debe ser positiva.")
        requested[line_id] = quantity

    locked_lines = {
        str(line.pk): line
        for line in source_document.lines.select_for_update().select_related(
            "product", "unit"
        ).filter(pk__in=requested)
    }
    if len(locked_lines) != len(requested):
        raise PosDomainError("INVALID_RETURN_LINE", "Una línea no pertenece a la venta seleccionada.")

    returned = {
        str(row["original_line_id"]): row["quantity"]
        for row in PosReturnLine.objects.filter(
            original_line_id__in=requested,
            pos_return__status=PosReturn.Status.COMPLETED,
        ).values("original_line_id").annotate(quantity=Sum("quantity"))
    }
    note_lines = []
    return_rows = []
    total = Decimal("0.00")
    original_lines_total = sum(
        (line.total for line in source_document.lines.all()), Decimal("0.00")
    )
    for line_id, quantity in requested.items():
        line = locked_lines[line_id]
        available = line.quantity - returned.get(line_id, Decimal("0"))
        if quantity > available:
            raise PosDomainError(
                "RETURN_QUANTITY_EXCEEDED",
                f"La devolución de {line.description} supera la cantidad pendiente ({available}).",
            )
        ratio = quantity / line.quantity
        line_total = (line.total * ratio).quantize(MONEY_QUANTUM)
        discount = (line.discount_amount * ratio).quantize(MONEY_QUANTUM)
        stock_quantity = (quantity * line.conversion_factor).quantize(Decimal("0.000001"))
        total += line_total
        note_lines.append({
            "product": line.product,
            "description": line.description,
            "quantity": quantity,
            "unit_price": line.unit_price,
            "unit": line.unit_id,
            "unit_code": line.unit_code,
            "discount_amount": discount,
            "tax_type": line.tax_type,
            "igv_rate": line.igv_rate,
            "sunat_product_code": line.sunat_product_code,
            "product_code": line.product_code,
            "memo": f"Devolución: {reason.strip()}",
        })
        return_rows.append((line, quantity, stock_quantity, line_total))

    selected_lines_total = total
    proportional_global_discount = Decimal("0.00")
    if source_document.global_discount_amount and original_lines_total > 0:
        proportional_global_discount = (
            source_document.global_discount_amount
            * selected_lines_total
            / original_lines_total
        ).quantize(MONEY_QUANTUM)
    if original_lines_total > 0:
        total = (
            source_document.total * selected_lines_total / original_lines_total
        ).quantize(MONEY_QUANTUM)

    fiscal_document = _fiscal_document_for_transaction(pos_transaction)
    credit_note = None
    if fiscal_document.document_type.code in {"01", "03"}:
        series = DocumentSeries.objects.filter(
            pk=credit_note_series_id,
            company_id=cash_session.company_id,
            store_id=cash_session.store_id,
            document_type__code="07",
            active=True,
        ).first()
        if series is None:
            raise PosDomainError(
                "CREDIT_NOTE_SERIES_REQUIRED",
                "Seleccione una serie válida de Nota de Crédito.",
            )
        try:
            credit_note = create_credit_note(
                sales_document_id=fiscal_document.pk,
                reason_code=reason_code,
                reason_description=reason.strip(),
                series=series,
                lines=note_lines,
                global_discount_amount=proportional_global_discount,
                created_by=created_by,
            )
            credit_note = issue_sales_document(credit_note.pk, issued_by=created_by)
        except (ValueError, ValidationError) as exc:
            raise PosDomainError("INVALID_CREDIT_NOTE", str(exc)) from exc
        total = credit_note.total

    means = MeansOfPayment.objects.filter(
        pk=refund_means_of_payment_id,
        company_id=cash_session.company_id,
        active=True,
    ).first()
    if means is None:
        raise PosDomainError("INVALID_REFUND_METHOD", "Seleccione un medio de devolución válido.")
    reference = (operation_reference or "").strip()
    if means.requires_reference and not reference:
        raise PosDomainError(
            "REFUND_REFERENCE_REQUIRED", "El medio de devolución requiere referencia."
        )
    if means.kind == MeansOfPayment.Kind.CASH and total > _expected_cash(cash_session):
        raise PosDomainError(
            "INSUFFICIENT_CASH_FOR_REFUND",
            "La caja no tiene efectivo esperado suficiente para realizar la devolución.",
        )

    pos_return = PosReturn(
        company=cash_session.company,
        store=cash_session.store,
        register=cash_session.register,
        cash_session=cash_session,
        original_transaction=pos_transaction,
        credit_note=credit_note,
        idempotency_key=idempotency_key,
        reason_code=reason_code if credit_note else "",
        reason=reason.strip(),
        currency=source_document.currency,
        total=total.quantize(MONEY_QUANTUM),
        created_by=created_by,
    )
    pos_return.full_clean()
    pos_return.save()
    for line, quantity, stock_quantity, line_total in return_rows:
        PosReturnLine.objects.create(
            pos_return=pos_return,
            original_line=line,
            product=line.product,
            quantity=quantity,
            stock_quantity=stock_quantity,
            total=line_total,
        )

    inventory_lines = [
        {"product_id": line.product_id, "quantity": stock_quantity, "unit_price": line.unit_price}
        for line, _, stock_quantity, _ in return_rows
        if line.product.tracks_inventory
    ]
    if inventory_lines:
        warehouse_id = source_document.warehouse_id or cash_session.register.default_warehouse_id
        if warehouse_id is None:
            raise PosDomainError("RETURN_WAREHOUSE_REQUIRED", "La devolución requiere un almacén.")
        movement_document = credit_note or source_document
        movement = register_entry(
            store_id=str(cash_session.store_id),
            warehouse_id=str(warehouse_id),
            date=timezone.now(),
            lines=inventory_lines,
            created_by=created_by,
            origin=MovementOrigin.SALE_REVERSAL,
            sales_document=movement_document,
            customer=source_document.customer,
            document_type=movement_document.document_type,
            series=movement_document.series_code,
            number=movement_document.number,
            reference_doc=str(pos_return.pk),
            reason="Devolución POS",
            description=f"Devolución de {source_document.series_code}-{source_document.number}",
        )
        movement = confirm_movement(movement, confirmed_by=created_by)
        pos_return.inventory_movement = movement
        pos_return.save(update_fields=("inventory_movement", "updated_at"))

    refund_payment = PosRefundPayment(
        pos_return=pos_return,
        cash_session=cash_session,
        means_of_payment=means,
        amount=pos_return.total,
        operation_reference=reference,
        created_by=created_by,
    )
    refund_payment.full_clean()
    refund_payment.save()
    _audit(
        pos_return,
        "REFUND",
        created_by,
        original_transaction_id=str(pos_transaction.pk),
        credit_note_id=str(credit_note.pk) if credit_note else None,
        inventory_movement_id=str(pos_return.inventory_movement_id) if pos_return.inventory_movement_id else None,
        amount=str(pos_return.total),
    )
    return pos_return, True


@transaction.atomic
def issue_pos_debit_note(
    *, pos_transaction_id, idempotency_key, series_id, reason_code, reason,
    line_items, created_by,
) -> tuple[SalesDocument, bool]:
    pos_transaction = PosTransaction.objects.select_for_update().select_related(
        "sales_document__document_type"
    ).get(pk=pos_transaction_id)
    original = _fiscal_document_for_transaction(pos_transaction)
    if original.document_type.code not in {"01", "03"}:
        raise PosDomainError("FISCAL_DOCUMENT_REQUIRED", "La nota de débito requiere factura o boleta.")
    internal_reference = f"POS-DN:{pos_transaction.pk}:{idempotency_key}"
    existing = SalesDocument.objects.filter(
        store_id=pos_transaction.store_id,
        document_type__code="08",
        internal_reference=internal_reference,
    ).first()
    if existing is not None:
        return existing, False
    series = DocumentSeries.objects.filter(
        pk=series_id,
        company_id=pos_transaction.company_id,
        store_id=pos_transaction.store_id,
        document_type__code="08",
        active=True,
    ).first()
    if series is None:
        raise PosDomainError("DEBIT_NOTE_SERIES_REQUIRED", "Seleccione una serie válida de Nota de Débito.")
    original_lines = {
        str(line.pk): line
        for line in pos_transaction.sales_document.lines.select_related("product", "unit")
    }
    lines = []
    for item in line_items:
        source = original_lines.get(str(item["line_id"]))
        if source is None:
            raise PosDomainError("INVALID_DEBIT_NOTE_LINE", "La línea no pertenece a la venta.")
        lines.append({
            "product": source.product,
            "description": item.get("description") or source.description,
            "quantity": item["quantity"],
            "unit_price": item["unit_price"],
            "unit": source.unit_id,
            "unit_code": source.unit_code,
            "discount_amount": Decimal("0.00"),
            "tax_type": source.tax_type,
            "igv_rate": source.igv_rate,
            "product_code": source.product_code,
            "memo": reason.strip(),
        })
    try:
        note = create_debit_note(
            sales_document_id=original.pk,
            reason_code=reason_code,
            reason_description=reason.strip(),
            series=series,
            lines=lines,
            internal_reference=internal_reference,
            created_by=created_by,
        )
        return issue_sales_document(note.pk, issued_by=created_by), True
    except (ValueError, ValidationError) as exc:
        raise PosDomainError("INVALID_DEBIT_NOTE", str(exc)) from exc


@transaction.atomic
def register_sales_payment(
    *, sales_document_id, cash_session_id, means_of_payment_id, amount,
    created_by, currency=None, exchange_rate=1, amount_in_sale_currency=None,
    received_amount=None, change_amount=None, operation_reference="",
    purpose=SalesPayment.Purpose.SALE_CHECKOUT, idempotency_key=None,
) -> SalesPayment:
    document = SalesDocument.objects.select_for_update(of=("self",)).select_related("store").get(
        pk=sales_document_id
    )
    session = CashSession.objects.select_for_update().get(pk=cash_session_id)
    means = MeansOfPayment.objects.get(pk=means_of_payment_id, active=True)
    if session.status != CashSession.Status.OPEN:
        raise PosDomainError("CASH_SESSION_CLOSED", "La sesion de caja esta cerrada.")
    if idempotency_key:
        existing = SalesPayment.objects.filter(
            cash_session=session, idempotency_key=idempotency_key
        ).first()
        if existing:
            if existing.sales_document_id != document.pk or existing.purpose != purpose:
                raise PosDomainError(
                    "PAYMENT_IDEMPOTENCY_CONFLICT",
                    "La clave de idempotencia ya fue utilizada por otro cobro.",
                )
            return existing
    if document.store_id != session.store_id or means.company_id != session.company_id:
        raise PosDomainError("PAYMENT_CONTEXT_MISMATCH", "El pago no pertenece al contexto de la venta.")
    try:
        pos_transaction = document.pos_transaction
    except PosTransaction.DoesNotExist:
        pos_transaction = None
    if (
        pos_transaction is not None
        and purpose == SalesPayment.Purpose.SALE_CHECKOUT
        and pos_transaction.cash_session_id != session.pk
    ):
        raise PosDomainError(
            "PAYMENT_SESSION_MISMATCH",
            "El pago debe registrarse en la sesion donde se inicio la venta POS.",
        )

    amount = _money(amount)
    try:
        exchange_rate = Decimal(str(exchange_rate))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PosDomainError("INVALID_AMOUNT", "El tipo de cambio no es valido.") from exc
    if amount <= 0 or not exchange_rate.is_finite() or exchange_rate <= 0:
        raise PosDomainError("INVALID_AMOUNT", "El importe y tipo de cambio deben ser positivos.")
    payment_currency = currency or document.currency
    if payment_currency != session.currency:
        raise PosDomainError(
            "CASH_SESSION_CURRENCY_MISMATCH",
            "La moneda del pago debe coincidir con la moneda de la sesion de caja.",
        )
    if amount_in_sale_currency is None:
        if payment_currency != document.currency:
            raise PosDomainError(
                "PAYMENT_CONVERSION_REQUIRED",
                "Debe indicar el importe convertido a la moneda de la venta.",
            )
        amount_in_sale_currency = amount
    amount_in_sale_currency = _money(amount_in_sale_currency, "importe aplicado")
    if payment_currency == document.currency and amount_in_sale_currency != amount:
        raise PosDomainError(
            "INVALID_PAYMENT_CONVERSION",
            "El importe aplicado debe coincidir con el pago cuando usan la misma moneda.",
        )

    # En el POS la referencia facilita la conciliación de billeteras y
    # transferencias, pero no debe impedir una venta rápida si el cajero aún
    # no dispone del número de operación.
    reference = (operation_reference or "").strip()

    received = _money(received_amount if received_amount is not None else amount, "importe recibido")
    change = _money(change_amount if change_amount is not None else 0, "vuelto")
    if means.kind == MeansOfPayment.Kind.CASH:
        if received < amount or change != received - amount:
            raise PosDomainError("INVALID_CHANGE", "El importe recibido y el vuelto no cuadran.")
    elif change != 0:
        raise PosDomainError("INVALID_CHANGE", "Solo un pago en efectivo puede generar vuelto.")

    already_paid = (
        document.pos_payments.filter(status=SalesPayment.Status.REGISTERED)
        .aggregate(total=Sum("amount_in_sale_currency"))["total"]
        or Decimal("0.00")
    )
    if already_paid + amount_in_sale_currency > document.total:
        raise PosDomainError("PAYMENT_EXCEEDS_TOTAL", "Los pagos superan el total de la venta.")

    payment = SalesPayment(
        sales_document=document,
        cash_session=session,
        means_of_payment=means,
        amount=amount,
        currency=payment_currency,
        exchange_rate=exchange_rate,
        amount_in_sale_currency=amount_in_sale_currency,
        received_amount=received,
        change_amount=change,
        operation_reference=reference,
        purpose=purpose,
        idempotency_key=idempotency_key,
        created_by=created_by,
    )
    payment.full_clean()
    payment.save()
    if pos_transaction is not None and pos_transaction.status == PosTransaction.Status.COMPLETED:
        paid_total = (
            document.pos_payments.filter(status=SalesPayment.Status.REGISTERED)
            .aggregate(total=Sum("amount_in_sale_currency"))["total"]
            or Decimal("0.00")
        ).quantize(MONEY_QUANTUM)
        pos_transaction.payment_status = (
            PosTransaction.PaymentStatus.PAID
            if paid_total == document.total
            else PosTransaction.PaymentStatus.PARTIAL
        )
        pos_transaction.save(update_fields=("payment_status", "updated_at"))
    _audit(
        payment, "REGISTER", created_by,
        sales_document_id=str(document.pk), amount=str(amount_in_sale_currency),
        means_of_payment_id=str(means.pk),
        cash_session_id=str(session.pk), purpose=purpose,
    )
    return payment


@transaction.atomic
def register_credit_collection(
    *, sales_document_id, cash_session_id, means_of_payment_id, amount,
    created_by, idempotency_key, currency=None, exchange_rate=1,
    amount_in_sale_currency=None, received_amount=None, change_amount=None,
    operation_reference="",
) -> SalesPayment:
    try:
        pos_transaction = PosTransaction.objects.select_for_update().get(
            sales_document_id=sales_document_id
        )
    except PosTransaction.DoesNotExist as exc:
        raise PosDomainError(
            "CREDIT_SALE_REQUIRED", "La cobranza debe corresponder a una venta POS a credito."
        ) from exc
    if (
        pos_transaction.status != PosTransaction.Status.COMPLETED
        or pos_transaction.payment_condition != PosTransaction.PaymentCondition.CREDIT
    ):
        raise PosDomainError(
            "CREDIT_SALE_REQUIRED", "Solo se pueden cobrar ventas POS a credito completadas."
        )
    if pos_transaction.payment_status == PosTransaction.PaymentStatus.PAID:
        raise PosDomainError("CREDIT_ALREADY_PAID", "La venta a credito ya fue pagada.")
    return register_sales_payment(
        sales_document_id=sales_document_id,
        cash_session_id=cash_session_id,
        means_of_payment_id=means_of_payment_id,
        amount=amount,
        created_by=created_by,
        currency=currency,
        exchange_rate=exchange_rate,
        amount_in_sale_currency=amount_in_sale_currency,
        received_amount=received_amount,
        change_amount=change_amount,
        operation_reference=operation_reference,
        purpose=SalesPayment.Purpose.CREDIT_COLLECTION,
        idempotency_key=idempotency_key,
    )


def _resolve_pos_lines(
    *, company_id, price_list, currency, line_items, allow_price_change, allow_discount,
) -> list[dict]:
    if not line_items:
        raise PosDomainError("SALE_LINES_REQUIRED", "Debe agregar al menos un producto.")

    product_ids = [
        str(item["product_id"])
        for item in line_items
        if item.get("line_type", "PRODUCT") == "PRODUCT" and item.get("product_id")
    ]
    products = {
        str(product.pk): product
        for product in Product.objects.select_related("unit").filter(
            pk__in=product_ids,
            company_id=company_id,
            active=True,
        )
    }
    if len(products) != len(set(product_ids)):
        raise PosDomainError(
            "INVALID_PRODUCT",
            "Uno o mas productos no existen, estan inactivos o pertenecen a otra empresa.",
        )

    list_prices = {}
    if price_list is not None:
        list_prices = {
            str(row.product_id): row.amount
            for row in ProductPrice.objects.filter(
                price_list=price_list,
                product_id__in=product_ids,
                product__company_id=company_id,
                currency=currency,
                active=True,
            )
        }

    resolved = []
    for item in line_items:
        is_manual = item.get("line_type", "PRODUCT") == "MANUAL"
        product = (
            _manual_pos_product(company_id, item.get("unit_id"))
            if is_manual
            else products[str(item["product_id"])]
        )
        quantity = Decimal(str(item["quantity"]))
        if not quantity.is_finite() or quantity <= 0:
            raise PosDomainError("INVALID_QUANTITY", "La cantidad debe ser mayor que cero.")

        requested_unit_id = item.get("unit_id") or product.unit_id
        conversion = ProductUnit.objects.filter(
            product=product,
            unit_id=requested_unit_id,
            active=True,
        ).first()
        if conversion is None:
            if str(requested_unit_id) != str(product.unit_id):
                raise PosDomainError(
                    "INVALID_PRODUCT_UNIT",
                    f"La unidad seleccionada no esta habilitada para {product.name}.",
                )
            has_default_sale = ProductUnit.objects.filter(
                product=product,
                is_default_sale=True,
            ).exists()
            has_default_purchase = ProductUnit.objects.filter(
                product=product,
                is_default_purchase=True,
            ).exists()
            conversion, _ = ProductUnit.objects.get_or_create(
                product=product,
                unit=product.unit,
                defaults={
                    "conversion_factor": 1,
                    "is_default_sale": not has_default_sale,
                    "is_default_purchase": not has_default_purchase,
                    "active": True,
                },
            )

        expected_commercial_price = list_prices.get(str(product.pk))
        if expected_commercial_price is None and currency == "PEN":
            expected_commercial_price = product.price_sale
        if (
            currency == "PEN"
            and conversion is not None
            and conversion.sale_price is not None
        ):
            expected_commercial_price = conversion.sale_price
        elif expected_commercial_price is not None and conversion is not None:
            expected_commercial_price = Decimal(str(expected_commercial_price)) * Decimal(
                str(conversion.conversion_factor)
            )
        if expected_commercial_price is None and not is_manual:
            raise PosDomainError(
                "PRICE_NOT_CONFIGURED",
                f"No existe un precio en {currency_symbol(currency)} para {product.name}.",
            )
        tax_type = item.get("tax_type") or product.tax_affectation
        effective_rate = tax_rate_for_company(company_id, affectation_type=tax_type)
        expected_price = (
            Decimal(str(item.get("unit_price"))).quantize(Decimal("0.000001"))
            if is_manual
            else split_final_price(
                expected_commercial_price,
                affectation_type=tax_type,
                tax_rate=effective_rate,
            ).unit_value
        )
        submitted_price = item.get("unit_price")
        unit_price = (
            expected_price
            if submitted_price is None
            else Decimal(str(submitted_price)).quantize(Decimal("0.000001"))
        )
        if not unit_price.is_finite() or unit_price < 0:
            raise PosDomainError("INVALID_PRICE", "El precio unitario no es valido.")
        if unit_price != expected_price and not is_manual and not allow_price_change:
            raise PosDomainError(
                "PRICE_CHANGE_NOT_AUTHORIZED",
                f"No tiene permiso para modificar el precio de {product.name}.",
            )

        discount = Decimal(str(item.get("discount_amount") or 0)).quantize(MONEY_QUANTUM)
        if not discount.is_finite() or discount < 0 or discount > unit_price * quantity:
            raise PosDomainError("INVALID_DISCOUNT", "El descuento de la linea no es valido.")
        if discount and not allow_discount:
            raise PosDomainError(
                "DISCOUNT_NOT_AUTHORIZED",
                "No tiene permiso para aplicar descuentos en el POS.",
            )

        resolved.append({
            "product": product,
            "description": (item.get("description") or product.name).strip(),
            "quantity": quantity,
            "unit_price": unit_price,
            "unit_id": requested_unit_id,
            "discount_amount": discount,
            "tax_type": tax_type,
            "igv_rate": effective_rate,
            "sunat_product_code": (item.get("sunat_product_code") or "").strip(),
            "product_code": (
                item.get("product_code") or ("SIN CODIGO" if is_manual else product.sku)
            ).strip(),
            "memo": (item.get("memo") or "").strip(),
        })
    return resolved


@transaction.atomic
def checkout_pos_sale(
    *, company_id, store_id, register_id, cash_session_id, idempotency_key,
    document_type_code, series_id, line_items, payment_items, cashier,
    customer_id=None, warehouse_id=None, price_list_id=None, currency="PEN",
    payment_condition=PosTransaction.PaymentCondition.CASH,
    payment_method_id=None, due_date=None,
    exchange_rate=1, global_discount_amount=0, global_discount_before_tax=False,
    notes="", device_identifier="", allow_price_change=False,
    allow_discount=False, allow_pricelist_change=False, save_as_draft=False,
) -> tuple[PosTransaction, bool]:
    session = (
        CashSession.objects.select_for_update(of=("self",))
        .select_related(
            "register__default_customer",
            "register__default_warehouse",
            "register__default_price_list",
            "company",
            "store",
        )
        .get(pk=cash_session_id)
    )
    if session.status != CashSession.Status.OPEN:
        raise PosDomainError("CASH_SESSION_REQUIRED", "Se requiere una sesion de caja abierta.")
    if (
        str(session.company_id) != str(company_id)
        or str(session.store_id) != str(store_id)
        or str(session.register_id) != str(register_id)
    ):
        raise PosDomainError("POS_CONTEXT_MISMATCH", "La caja no pertenece al contexto activo.")
    if currency != session.currency:
        raise PosDomainError(
            "CASH_SESSION_CURRENCY_MISMATCH",
            "La moneda de la venta debe coincidir con la moneda de la sesion de caja.",
        )

    existing = PosTransaction.objects.filter(
        company_id=company_id,
        register_id=register_id,
        idempotency_key=idempotency_key,
    ).first()
    if existing is not None and existing.status != PosTransaction.Status.DRAFT:
        return existing, False

    if document_type_code not in {"NV", "01", "03"}:
        raise PosDomainError(
            "INVALID_DOCUMENT_TYPE",
            "El POS solo puede emitir Nota de Venta, boleta o factura.",
        )
    document_type = DocumentType.objects.filter(
        code=document_type_code,
        active=True,
    ).first()
    if document_type is None:
        raise PosDomainError("INVALID_DOCUMENT_TYPE", "El tipo de documento no esta disponible.")
    series = DocumentSeries.objects.filter(
        pk=series_id,
        company_id=company_id,
        store_id=store_id,
        document_type=document_type,
        active=True,
    ).first()
    if series is None:
        raise PosDomainError("INVALID_DOCUMENT_SERIES", "La serie no pertenece al POS activo.")

    customer_pk = customer_id or session.register.default_customer_id
    customer = Customer.objects.filter(
        pk=customer_pk,
        company_id=company_id,
        active=True,
    ).first()
    if customer is None:
        raise PosDomainError("CUSTOMER_REQUIRED", "Debe seleccionar un cliente valido.")
    if document_type_code == "01" and (
        customer.document_type != "6" or len(customer.document_number.strip()) != 11
    ):
        raise PosDomainError("RUC_REQUIRED", "La factura requiere un cliente con RUC valido.")

    if payment_condition not in PosTransaction.PaymentCondition.values:
        raise PosDomainError("INVALID_PAYMENT_CONDITION", "La condicion de pago no es valida.")
    payment_method = None
    if payment_method_id:
        payment_method = PaymentMethod.objects.filter(
            pk=payment_method_id,
            company_id=company_id,
            active=True,
        ).first()
        if payment_method is None:
            raise PosDomainError(
                "INVALID_PAYMENT_METHOD",
                "La condicion comercial seleccionada no es valida.",
            )
    elif payment_condition == PosTransaction.PaymentCondition.CASH:
        payment_method = PaymentMethod.objects.filter(
            company_id=company_id,
            active=True,
            is_credit=False,
            immediate_payment=True,
        ).order_by("name").first()

    if payment_method is not None and (
        payment_method.is_credit
        != (payment_condition == PosTransaction.PaymentCondition.CREDIT)
    ):
        raise PosDomainError(
            "PAYMENT_METHOD_CONDITION_MISMATCH",
            "La condicion comercial no coincide con contado o credito.",
        )
    if payment_condition == PosTransaction.PaymentCondition.CREDIT:
        if payment_method is None:
            raise PosDomainError(
                "CREDIT_PAYMENT_METHOD_REQUIRED",
                "Seleccione una condicion comercial de credito.",
            )
        if customer.document_type == "0" or not customer.document_number.strip():
            raise PosDomainError(
                "IDENTIFIED_CUSTOMER_REQUIRED",
                "La venta a credito requiere un cliente identificado.",
            )
        if due_date is None or due_date < timezone.localdate():
            raise PosDomainError(
                "INVALID_CREDIT_DUE_DATE",
                "La fecha de vencimiento del credito no puede ser anterior a hoy.",
            )
    else:
        due_date = None

    selected_price_list_id = price_list_id or session.register.default_price_list_id
    price_list = None
    if selected_price_list_id:
        price_list = PriceList.objects.filter(
            pk=selected_price_list_id,
            company_id=company_id,
            active=True,
        ).first()
        if price_list is None:
            raise PosDomainError("INVALID_PRICE_LIST", "La lista de precios no es valida.")
        if (
            str(price_list.pk) != str(session.register.default_price_list_id)
            and not allow_pricelist_change
        ):
            raise PosDomainError(
                "PRICE_LIST_CHANGE_NOT_AUTHORIZED",
                "No tiene permiso para cambiar la lista de precios.",
            )

    global_discount = _money(global_discount_amount, "descuento general")
    if global_discount and not allow_discount:
        raise PosDomainError(
            "DISCOUNT_NOT_AUTHORIZED",
            "No tiene permiso para aplicar descuentos en el POS.",
        )
    lines = _resolve_pos_lines(
        company_id=company_id,
        price_list=price_list,
        currency=currency,
        line_items=line_items,
        allow_price_change=allow_price_change,
        allow_discount=allow_discount,
    )

    selected_warehouse_id = warehouse_id or session.register.default_warehouse_id
    warehouse = None
    if selected_warehouse_id:
        warehouse = Warehouse.objects.filter(
            pk=selected_warehouse_id,
            store_id=store_id,
            active=True,
        ).first()
        if warehouse is None:
            raise PosDomainError("INVALID_WAREHOUSE", "El almacen no pertenece a la sucursal.")
    if any(line["product"].tracks_inventory for line in lines) and warehouse is None:
        raise PosDomainError("WAREHOUSE_REQUIRED", "Debe configurar un almacen para el POS.")

    try:
        document_kwargs = {
            "store_id": str(store_id),
            "customer": customer,
            "document_type": document_type,
            "series": series,
            "lines": lines,
            "issue_date": timezone.now(),
            "currency": currency,
            "exchange_rate": exchange_rate,
            "price_list": price_list,
            "payment_method": payment_method,
            "due_date": due_date,
            "register_inventory_movement": True,
            "warehouse": warehouse,
            "global_discount_amount": global_discount,
            "global_discount_before_tax": global_discount_before_tax,
            "global_discount_from_total": True,
            "line_discount_from_total": True,
            "notes": (notes or "").strip(),
        }
        if existing is not None:
            if existing.cash_session_id != session.pk:
                raise PosDomainError(
                    "DRAFT_SESSION_MISMATCH",
                    "El borrador pertenece a otra sesion de caja.",
                )
            if existing.sales_document.pos_payments.filter(
                status=SalesPayment.Status.REGISTERED
            ).exists():
                raise PosDomainError(
                    "DRAFT_HAS_PAYMENTS", "Un borrador no puede contener pagos registrados."
                )
            document = update_sales_document_draft(
                existing.sales_document_id,
                updated_by=cashier,
                **document_kwargs,
            )
            pos_transaction = existing
            pos_transaction.cashier = cashier
            pos_transaction.payment_condition = payment_condition
            pos_transaction.billing_status = (
                PosTransaction.BillingStatus.INVOICED
                if document_type_code in ("01", "03")
                else PosTransaction.BillingStatus.NOT_REQUESTED
            )
        else:
            document = create_sales_document_draft(
                created_by=cashier,
                **document_kwargs,
            )
            pos_transaction, _ = start_pos_transaction(
                cash_session_id=session.pk,
                sales_document_id=document.pk,
                idempotency_key=idempotency_key,
                cashier=cashier,
                device_identifier=device_identifier,
                payment_condition=payment_condition,
            )
        if save_as_draft:
            pos_transaction.status = PosTransaction.Status.DRAFT
            pos_transaction.completed_at = None
            pos_transaction.save(update_fields=(
                "status", "completed_at", "cashier", "payment_condition",
                "billing_status", "updated_at",
            ))
            _audit(pos_transaction, "SUSPEND", cashier, sales_document_id=str(document.pk))
            return PosTransaction.objects.select_related(
                "sales_document", "sales_document__document_type", "cash_session",
                "register", "cashier",
            ).get(pk=pos_transaction.pk), existing is None

        pos_transaction.status = PosTransaction.Status.PROCESSING
        pos_transaction.save(update_fields=(
            "status", "cashier", "payment_condition", "billing_status", "updated_at",
        ))
        issue_sales_document(document.pk, issued_by=cashier)
        for item in payment_items:
            register_sales_payment(
                sales_document_id=document.pk,
                cash_session_id=session.pk,
                means_of_payment_id=item["means_of_payment_id"],
                amount=item["amount"],
                currency=item.get("currency") or currency,
                exchange_rate=item.get("exchange_rate") or 1,
                amount_in_sale_currency=item.get("amount_in_sale_currency"),
                received_amount=item.get("received_amount"),
                change_amount=item.get("change_amount"),
                operation_reference=item.get("operation_reference") or "",
                created_by=cashier,
            )
        complete_pos_transaction(
            pos_transaction.pk,
            completed_by=cashier,
            allow_outstanding=(
                payment_condition == PosTransaction.PaymentCondition.CREDIT
            ),
        )
    except PosDomainError:
        raise
    except (ValueError, ValidationError) as exc:
        raise PosDomainError("INVALID_POS_SALE", "; ".join(getattr(exc, "messages", [str(exc)]))) from exc

    return PosTransaction.objects.select_related(
        "sales_document", "cash_session", "register", "cashier"
    ).get(pk=pos_transaction.pk), existing is None


def _validate_invoice_source(source: SalesDocument) -> PosTransaction:
    try:
        pos_transaction = PosTransaction.objects.select_for_update().get(
            sales_document=source
        )
    except PosTransaction.DoesNotExist as exc:
        raise PosDomainError("NOT_A_POS_TICKET", "La Nota de Venta no proviene del POS.") from exc
    if pos_transaction.status != PosTransaction.Status.COMPLETED:
        raise PosDomainError("POS_TICKET_NOT_COMPLETED", "El ticket POS no esta completado.")
    if source.status != "ISSUED":
        raise PosDomainError("POS_TICKET_NOT_ISSUED", "La Nota de Venta debe estar emitida.")
    paid = (
        source.pos_payments.filter(status=SalesPayment.Status.REGISTERED)
        .aggregate(total=Sum("amount_in_sale_currency"))["total"]
        or Decimal("0.00")
    )
    if paid.quantize(MONEY_QUANTUM) != source.total:
        raise PosDomainError("POS_TICKET_NOT_PAID", "La Nota de Venta debe estar totalmente pagada.")
    return pos_transaction


@transaction.atomic
def request_consolidated_invoice(*, source_document_ids, requested_by=None) -> list[PosTransaction]:
    source_ids = list(dict.fromkeys(str(value) for value in source_document_ids))
    if not source_ids:
        raise PosDomainError("INVOICE_SOURCES_REQUIRED", "Debe seleccionar al menos un ticket.")
    sources = list(
        SalesDocument.objects.select_for_update(of=("self",))
        .select_related("store", "customer", "document_type")
        .filter(pk__in=source_ids)
    )
    if len(sources) != len(source_ids):
        raise SalesDocument.DoesNotExist

    source_by_id = {str(source.pk): source for source in sources}
    ordered_sources = [source_by_id[source_id] for source_id in source_ids]
    first = ordered_sources[0]
    business_date = None
    transactions = []
    for source in ordered_sources:
        pos_transaction = _validate_invoice_source(source)
        transaction_date = timezone.localdate(pos_transaction.started_at)
        business_date = business_date or transaction_date
        if (
            source.customer_id is None
            or source.customer.document_type != "6"
            or len(source.customer.document_number.strip()) != 11
        ):
            raise PosDomainError(
                "IDENTIFIED_CUSTOMER_REQUIRED",
                "La factura consolidada requiere un cliente identificado con RUC.",
            )
        if (
            source.store_id != first.store_id
            or source.customer_id != first.customer_id
            or source.currency != first.currency
        ):
            raise PosDomainError(
                "INVOICE_SOURCE_CONTEXT_MISMATCH",
                "Los tickets deben ser de la misma sucursal, cliente y moneda.",
            )
        if transaction_date != business_date:
            raise PosDomainError(
                "INVOICE_SOURCE_DATE_MISMATCH",
                "Los tickets deben pertenecer a la misma fecha operativa.",
            )
        if pos_transaction.billing_status == PosTransaction.BillingStatus.INVOICED:
            raise PosDomainError("POS_TICKET_ALREADY_INVOICED", "El ticket ya fue facturado.")
        transactions.append(pos_transaction)

    for pos_transaction in transactions:
        pos_transaction.billing_status = PosTransaction.BillingStatus.INVOICE_REQUESTED
        pos_transaction.failure_code = ""
        pos_transaction.failure_message = ""
        pos_transaction.save(
            update_fields=("billing_status", "failure_code", "failure_message", "updated_at")
        )
        _audit(pos_transaction, "REQUEST_INVOICE", requested_by)
    return transactions


@transaction.atomic
def link_tickets_to_consolidated_invoice(
    *, source_document_ids, target_document_id, created_by=None,
) -> list[SalesDocumentSource]:
    source_ids = list(dict.fromkeys(str(value) for value in source_document_ids))
    target_id = str(target_document_id)
    if not source_ids:
        raise PosDomainError("INVOICE_SOURCES_REQUIRED", "Debe seleccionar al menos un ticket.")
    if target_id in source_ids:
        raise PosDomainError("INVALID_INVOICE_SOURCE", "La factura no puede ser su propio origen.")

    document_ids = sorted((*source_ids, target_id))
    locked = {
        str(document.pk): document
        for document in SalesDocument.objects.select_for_update(of=("self",))
        .select_related("store", "customer", "document_type")
        .filter(pk__in=document_ids)
    }
    target = locked.get(target_id)
    sources = [locked.get(source_id) for source_id in source_ids]
    if target is None or any(source is None for source in sources):
        raise SalesDocument.DoesNotExist
    if target.status != "ISSUED":
        raise PosDomainError(
            "INVALID_INVOICE_TARGET",
            "La factura destino debe estar emitida antes de consolidar los tickets.",
        )

    source_total = sum((source.total for source in sources), Decimal("0.00"))
    if source_total.quantize(MONEY_QUANTUM) != target.total:
        raise PosDomainError(
            "CONSOLIDATED_TOTAL_MISMATCH",
            "El total de la factura no coincide con los tickets seleccionados.",
        )

    links = []
    for source in sources:
        pos_transaction = _validate_invoice_source(source)
        link = SalesDocumentSource(
            source_document=source,
            target_document=target,
            created_by=created_by,
        )
        try:
            link.full_clean()
        except ValidationError as exc:
            raise PosDomainError("INVALID_INVOICE_SOURCE", "; ".join(exc.messages)) from exc
        link.save()
        pos_transaction.billing_status = PosTransaction.BillingStatus.INVOICED
        pos_transaction.save(update_fields=("billing_status", "updated_at"))
        _audit(
            link, "LINK", created_by,
            source_document_id=str(source.pk), target_document_id=str(target.pk),
        )
        links.append(link)
    return links


def link_ticket_to_consolidated_invoice(
    *, source_document_id, target_document_id, created_by=None,
) -> SalesDocumentSource:
    return link_tickets_to_consolidated_invoice(
        source_document_ids=[source_document_id],
        target_document_id=target_document_id,
        created_by=created_by,
    )[0]


@transaction.atomic
def create_consolidated_invoice(
    *, source_document_ids, invoice_series_id, created_by,
) -> tuple[SalesDocument, list[SalesDocumentSource]]:
    source_ids = list(dict.fromkeys(str(value) for value in source_document_ids))
    if not source_ids:
        raise PosDomainError("INVOICE_SOURCES_REQUIRED", "Debe seleccionar al menos un ticket.")
    sources = list(
        SalesDocument.objects.select_for_update(of=("self",))
        .select_related("store__company", "customer", "document_type")
        .prefetch_related("lines__product", "lines__unit")
        .filter(pk__in=source_ids)
    )
    if len(sources) != len(source_ids):
        raise SalesDocument.DoesNotExist
    by_id = {str(source.pk): source for source in sources}
    sources = [by_id[source_id] for source_id in source_ids]
    first = sources[0]

    transactions = []
    business_date = None
    for source in sources:
        pos_transaction = _validate_invoice_source(source)
        transaction_date = timezone.localdate(pos_transaction.started_at)
        business_date = business_date or transaction_date
        if (
            source.customer_id is None
            or source.customer.document_type != "6"
            or len(source.customer.document_number.strip()) != 11
        ):
            raise PosDomainError(
                "IDENTIFIED_CUSTOMER_REQUIRED",
                "La factura consolidada requiere un cliente identificado con RUC.",
            )
        if (
            source.store_id != first.store_id
            or source.customer_id != first.customer_id
            or source.currency != first.currency
        ):
            raise PosDomainError(
                "INVOICE_SOURCE_CONTEXT_MISMATCH",
                "Los tickets deben ser de la misma sucursal, cliente y moneda.",
            )
        if transaction_date != business_date:
            raise PosDomainError(
                "INVOICE_SOURCE_DATE_MISMATCH",
                "Los tickets deben pertenecer a la misma fecha operativa.",
            )
        if pos_transaction.billing_status == PosTransaction.BillingStatus.INVOICED:
            raise PosDomainError("POS_TICKET_ALREADY_INVOICED", "El ticket ya fue facturado.")
        transactions.append(pos_transaction)

    invoice_type = DocumentType.objects.filter(code="01", active=True).first()
    if invoice_type is None:
        raise PosDomainError("INVALID_DOCUMENT_TYPE", "El tipo Factura no esta disponible.")
    series = DocumentSeries.objects.filter(
        pk=invoice_series_id,
        company_id=first.store.company_id,
        store_id=first.store_id,
        document_type=invoice_type,
        active=True,
    ).first()
    if series is None:
        raise PosDomainError("INVALID_DOCUMENT_SERIES", "La serie de factura no es valida.")

    discount_modes = {
        source.global_discount_before_tax
        for source in sources
        if source.global_discount_amount
    }
    if len(discount_modes) > 1:
        raise PosDomainError(
            "INCOMPATIBLE_GLOBAL_DISCOUNTS",
            "No se pueden consolidar tickets con modalidades distintas de descuento general.",
        )
    global_discount = sum(
        (source.global_discount_amount for source in sources),
        Decimal("0.00"),
    )
    global_discount_before_tax = next(iter(discount_modes), False)
    lines = []
    for source in sources:
        for line in source.lines.all():
            lines.append({
                "product": line.product,
                "description": line.description,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "unit_id": line.unit_id,
                "discount_amount": line.discount_amount,
                "tax_type": line.tax_type,
                "igv_rate": line.igv_rate,
                "sunat_product_code": line.sunat_product_code,
                "product_code": line.product_code,
                "memo": line.memo,
            })

    try:
        invoice = create_sales_document_draft(
            store_id=str(first.store_id),
            customer=first.customer,
            document_type=invoice_type,
            series=series,
            lines=lines,
            created_by=created_by,
            issue_date=timezone.now(),
            currency=first.currency,
            exchange_rate=first.exchange_rate,
            register_inventory_movement=False,
            global_discount_amount=global_discount,
            global_discount_before_tax=global_discount_before_tax,
            notes="Factura consolidada de tickets POS: " + ", ".join(
                pos_transaction.ticket_code for pos_transaction in transactions
            ),
        )
        issue_sales_document(invoice.pk, issued_by=created_by)
        links = link_tickets_to_consolidated_invoice(
            source_document_ids=source_ids,
            target_document_id=invoice.pk,
            created_by=created_by,
        )
    except PosDomainError:
        raise
    except (ValueError, ValidationError) as exc:
        raise PosDomainError(
            "INVALID_CONSOLIDATED_INVOICE",
            "; ".join(getattr(exc, "messages", [str(exc)])),
        ) from exc
    return invoice, links


def _expected_cash(session: CashSession) -> Decimal:
    return calculate_cash_session_totals(session)["expected_cash_total"]


@transaction.atomic
def close_cash_session(
    *, cash_session_id, closed_by, counted_cash_total, denominations=None,
    next_opening_total=0, safe_deposit_total=None, bank_deposit_total=0,
    bank_deposit_destination="", note="", tender_counts=None,
    difference_authorized_by=None,
) -> CashSession:
    session = CashSession.objects.select_for_update().get(pk=cash_session_id)
    if session.status != CashSession.Status.OPEN:
        raise PosDomainError("CASH_SESSION_CLOSED", "La sesion de caja ya esta cerrada.")
    if session.transactions.filter(
        status__in=(
            PosTransaction.Status.DRAFT,
            PosTransaction.Status.PAYMENT_PENDING,
            PosTransaction.Status.PROCESSING,
        )
    ).exists():
        raise PosDomainError(
            "CLOSE_HAS_PENDING_OPERATIONS", "Existen ventas POS pendientes de completar."
        )
    if session.transactions.filter(
        billing_status__in=(
            PosTransaction.BillingStatus.INVOICE_REQUESTED,
            PosTransaction.BillingStatus.INVOICE_PROCESSING,
            PosTransaction.BillingStatus.INVOICE_FAILED,
        )
    ).exists():
        raise PosDomainError(
            "CLOSE_HAS_PENDING_INVOICES", "Existen solicitudes de factura pendientes."
        )

    counted = _money(counted_cash_total, "efectivo contado")
    next_opening = _money(next_opening_total, "fondo siguiente")
    bank_deposit = _money(bank_deposit_total, "depósito bancario")
    safe_deposit = (
        counted - next_opening - bank_deposit
        if safe_deposit_total is None
        else _money(safe_deposit_total, "importe para caja fuerte")
    )
    if any(value < 0 for value in (counted, next_opening, safe_deposit, bank_deposit)):
        raise PosDomainError("INVALID_CLOSING_COUNT", "Los importes del cierre no son validos.")
    if next_opening + safe_deposit + bank_deposit != counted:
        raise PosDomainError(
            "CASH_ALLOCATION_MISMATCH",
            "El efectivo contado debe distribuirse totalmente entre gaveta, caja fuerte y banco.",
        )
    bank_destination = (bank_deposit_destination or "").strip()
    if bank_deposit > 0 and not bank_destination:
        raise PosDomainError(
            "BANK_DESTINATION_REQUIRED", "Indique el banco o destino del depósito."
        )
    if denominations is not None:
        denomination_total = _create_denomination_counts(
            session, CashDenominationCount.Phase.CLOSING, denominations
        )
        if denomination_total != counted:
            raise PosDomainError(
                "CLOSING_COUNT_MISMATCH",
                "El conteo por denominaciones no coincide con el efectivo contado.",
            )

    cash_totals = calculate_cash_session_totals(session)
    expected = cash_totals["expected_cash_total"]
    cash_difference = counted - expected
    if cash_difference != 0 and difference_authorized_by is None:
        raise PosDomainError(
            "CASH_DIFFERENCE_AUTHORIZATION_REQUIRED",
            "Una diferencia de caja requiere autorizacion de un responsable.",
        )
    expected_tender_rows = list(
        session.sales_payments.filter(status=SalesPayment.Status.REGISTERED)
        .values("means_of_payment", "means_of_payment__kind")
        .annotate(total=Sum("amount_in_sale_currency"))
    )
    expected_by_tender = {
        str(row["means_of_payment"]): row["total"]
        for row in expected_tender_rows
    }
    refund_tender_rows = list(
        session.refund_payments.values(
            "means_of_payment", "means_of_payment__kind"
        ).annotate(total=Sum("amount"))
    )
    for row in refund_tender_rows:
        means_id = str(row["means_of_payment"])
        expected_by_tender[means_id] = (
            expected_by_tender.get(means_id, Decimal("0.00")) - row["total"]
        )
    movement_tender_rows = list(
        session.cash_movements.exclude(means_of_payment__isnull=True)
        .values("means_of_payment", "movement_type")
        .annotate(total=Sum("amount"))
    )
    for row in movement_tender_rows:
        means_id = str(row["means_of_payment"])
        direction = (
            Decimal("1.00")
            if row["movement_type"] == CashMovement.MovementType.PAY_IN
            else Decimal("-1.00")
        )
        expected_by_tender[means_id] = (
            expected_by_tender.get(means_id, Decimal("0.00")) + row["total"] * direction
        )
    required_tender_ids = {
        means_id
        for means_id, amount in expected_by_tender.items()
        if amount != 0 and MeansOfPayment.objects.filter(
            pk=means_id
        ).exclude(kind=MeansOfPayment.Kind.CASH).exists()
    }
    declared_means = set()
    has_tender_difference = False
    for declaration in tender_counts or []:
        means_id = str(declaration["means_of_payment_id"])
        if means_id in declared_means:
            raise PosDomainError(
                "DUPLICATE_TENDER_DECLARATION",
                "Un medio de pago no puede declararse mas de una vez.",
            )
        declared_means.add(means_id)
        if not MeansOfPayment.objects.filter(
            pk=means_id,
            company=session.company,
        ).exists():
            raise PosDomainError(
                "PAYMENT_CONTEXT_MISMATCH",
                "El medio de pago declarado no pertenece a la empresa de la caja.",
            )
        declared = _money(declaration["counted_amount"], "importe declarado")
        tender_expected = _money(expected_by_tender.get(means_id, 0), "importe esperado")
        tender_difference = declared - tender_expected
        has_tender_difference = has_tender_difference or tender_difference != 0
        if tender_difference != 0 and difference_authorized_by is None:
            raise PosDomainError(
                "TENDER_DIFFERENCE_AUTHORIZATION_REQUIRED",
                "Una diferencia en medios de pago requiere autorizacion de un responsable.",
            )
        CashTenderDeclaration.objects.update_or_create(
            cash_session=session,
            means_of_payment_id=means_id,
            defaults={
                "expected_amount": tender_expected,
                "counted_amount": declared,
                "difference": tender_difference,
            },
        )
    if required_tender_ids - declared_means:
        raise PosDomainError(
            "TENDER_DECLARATION_REQUIRED",
            "Debe conciliar todos los medios de pago no efectivos antes de cerrar.",
        )
    clean_note = (note or "").strip()
    if (cash_difference != 0 or has_tender_difference) and not clean_note:
        raise PosDomainError(
            "CASH_DIFFERENCE_REASON_REQUIRED",
            "Debe indicar una observacion que explique la diferencia del cierre.",
        )

    session.status = CashSession.Status.CLOSED
    session.closed_by = closed_by
    session.closed_at = timezone.now()
    session.expected_cash_total = expected
    session.counted_cash_total = counted
    session.cash_difference = cash_difference
    session.difference_authorized_by = difference_authorized_by
    session.next_opening_total = next_opening
    session.safe_deposit_total = safe_deposit
    session.bank_deposit_total = bank_deposit
    session.bank_deposit_destination = bank_destination
    session.closing_note = clean_note
    session.version += 1
    session.full_clean()
    session.save()
    if safe_deposit > 0:
        CashSafeMovement.objects.create(
            company=session.company, store=session.store, cash_session=session,
            direction=CashSafeMovement.Direction.IN,
            movement_type=CashSafeMovement.MovementType.CLOSING_DEPOSIT,
            amount=safe_deposit, currency=session.currency,
            destination="Caja fuerte de tienda",
            notes=f"Cierre de caja N.º {session.session_number}",
            created_by=closed_by, authorized_by=closed_by,
        )
    _audit(
        session, "CLOSE", closed_by,
        expected_cash_total=str(expected), counted_cash_total=str(counted),
        cash_difference=str(session.cash_difference),
        opening_total=str(cash_totals["opening_total"]),
        cash_payments=str(cash_totals["cash_payments"]),
        cash_refunds=str(cash_totals["cash_refunds"]),
        cash_in=str(cash_totals["cash_in"]),
        cash_out=str(cash_totals["cash_out"]),
        next_opening_total=str(next_opening),
        safe_deposit_total=str(safe_deposit),
        bank_deposit_total=str(bank_deposit),
        bank_deposit_destination=bank_destination,
        closing_note=clean_note,
        difference_authorized_by_id=(
            str(difference_authorized_by.pk) if difference_authorized_by else None
        ),
    )
    return session
