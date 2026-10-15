from decimal import Decimal

from django.db.models import Q, Sum

from .models import CashSafeMovement


def get_cash_safe_balances(movements):
    movements = movements.filter(
        status__in=(CashSafeMovement.Status.POSTED, CashSafeMovement.Status.REVERSED)
    )
    balances = []
    for currency in ("PEN", "USD"):
        totals = movements.filter(currency=currency).aggregate(
            incoming=Sum("amount", filter=Q(direction=CashSafeMovement.Direction.IN)),
            outgoing=Sum("amount", filter=Q(direction=CashSafeMovement.Direction.OUT)),
        )
        incoming = totals["incoming"] or Decimal("0.00")
        outgoing = totals["outgoing"] or Decimal("0.00")
        balances.append({
            "currency": currency,
            "incoming": incoming,
            "outgoing": outgoing,
            "balance": incoming - outgoing,
        })
    return balances


def get_cash_safe_report_movements(
    *, company_id, store_id, date_from=None, date_to=None, currency="",
    direction="", movement_type="", fund_id=None, search="",
):
    movements = CashSafeMovement.objects.filter(
        company_id=company_id, store_id=store_id
    ).select_related(
        "fund", "created_by", "authorized_by", "supplier",
        "purchase_document", "expense_category",
    ).order_by("created_at", "id")
    if date_from:
        movements = movements.filter(created_at__date__gte=date_from)
    if date_to:
        movements = movements.filter(created_at__date__lte=date_to)
    if currency in {"PEN", "USD"}:
        movements = movements.filter(currency=currency)
    if direction in dict(CashSafeMovement.Direction.choices):
        movements = movements.filter(direction=direction)
    if movement_type in dict(CashSafeMovement.MovementType.choices):
        movements = movements.filter(movement_type=movement_type)
    if fund_id:
        movements = movements.filter(fund_id=fund_id)
    if search:
        movements = movements.filter(
            Q(recipient_name__icontains=search) | Q(destination__icontains=search)
            | Q(reference__icontains=search) | Q(notes__icontains=search)
        )
    return movements
