from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, OuterRef, Q, QuerySet, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.sales.models import DocumentSeries, MeansOfPayment, PaymentMethod

from .models import (
    CashMovement, CashSession, PosRefundPayment, PosRegister, PosTransaction, SalesPayment,
)


MONEY_QUANTUM = Decimal("0.01")


def calculate_cash_session_totals(cash_session: CashSession) -> dict:
    """Canonical backend calculation used by live summaries and final closure."""
    cash_payments = (
        cash_session.sales_payments.filter(
            status=SalesPayment.Status.REGISTERED,
            means_of_payment__kind=MeansOfPayment.Kind.CASH,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    cash_refunds = (
        cash_session.refund_payments.filter(
            means_of_payment__kind=MeansOfPayment.Kind.CASH,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    cash_movement_queryset = cash_session.cash_movements.filter(
        Q(means_of_payment__isnull=True) | Q(means_of_payment__kind=MeansOfPayment.Kind.CASH)
    )
    movements = {
        row["movement_type"]: row["total"]
        for row in cash_movement_queryset.values("movement_type").annotate(total=Sum("amount"))
    }
    cash_in = movements.get(CashMovement.MovementType.PAY_IN, Decimal("0.00"))
    cash_out = sum(
        (
            movements.get(movement_type, Decimal("0.00"))
            for movement_type in (
                CashMovement.MovementType.PAY_OUT,
                CashMovement.MovementType.WITHDRAWAL,
                CashMovement.MovementType.DEPOSIT,
            )
        ),
        Decimal("0.00"),
    )
    expected = (
        cash_session.opening_total + cash_payments + cash_in - cash_out - cash_refunds
    ).quantize(MONEY_QUANTUM)
    return {
        "opening_total": cash_session.opening_total.quantize(MONEY_QUANTUM),
        "cash_payments": cash_payments.quantize(MONEY_QUANTUM),
        "cash_refunds": cash_refunds.quantize(MONEY_QUANTUM),
        "cash_in": cash_in.quantize(MONEY_QUANTUM),
        "cash_out": cash_out.quantize(MONEY_QUANTUM),
        "expected_cash_total": expected,
    }


def get_pos_registers(*, company_id, store_id, active_only=True) -> QuerySet:
    queryset = PosRegister.objects.filter(company_id=company_id, store_id=store_id)
    if active_only:
        queryset = queryset.filter(active=True)
    return queryset.select_related(
        "store",
        "default_warehouse",
        "default_price_list",
        "default_customer",
        "default_document_type",
    ).order_by("code")


def get_open_session(*, company_id, store_id, register_id):
    return (
        CashSession.objects.filter(
            company_id=company_id,
            store_id=store_id,
            register_id=register_id,
            status=CashSession.Status.OPEN,
        )
        .select_related("register", "opened_by")
        .first()
    )


def get_cash_session_history(*, company_id, store_id) -> QuerySet:
    """Return session history with collection totals without multiplying joins."""
    registered_payments = (
        SalesPayment.objects.filter(
            cash_session_id=OuterRef("pk"),
            status=SalesPayment.Status.REGISTERED,
        )
        .values("cash_session_id")
        .annotate(total=Sum("amount_in_sale_currency"))
        .values("total")[:1]
    )
    refunds = (
        PosRefundPayment.objects.filter(cash_session_id=OuterRef("pk"))
        .values("cash_session_id")
        .annotate(total=Sum("amount"))
        .values("total")[:1]
    )
    money_field = DecimalField(max_digits=14, decimal_places=2)
    return (
        CashSession.objects.filter(company_id=company_id, store_id=store_id)
        .select_related("register", "store", "opened_by", "closed_by")
        .annotate(
            collected_total=Coalesce(
                Subquery(registered_payments, output_field=money_field),
                Value(Decimal("0.00"), output_field=money_field),
            ),
            refunded_total=Coalesce(
                Subquery(refunds, output_field=money_field),
                Value(Decimal("0.00"), output_field=money_field),
            ),
        )
        .annotate(
            net_collected_total=ExpressionWrapper(
                F("collected_total") - F("refunded_total"), output_field=money_field
            )
        )
        .order_by("-opened_at")
    )


def get_cash_session_summary(cash_session: CashSession) -> dict:
    """Resumen operativo para arqueo y cierre de una sesión de caja."""
    payments = list(
        cash_session.sales_payments.filter(status=SalesPayment.Status.REGISTERED)
        .values(
            "means_of_payment_id",
            "means_of_payment__name",
            "means_of_payment__kind",
        )
        .annotate(total=Sum("amount_in_sale_currency"), operations=Count("id"))
        .order_by("means_of_payment__kind", "means_of_payment__name")
    )
    refunds = list(
        cash_session.refund_payments.values(
            "means_of_payment_id",
            "means_of_payment__name",
            "means_of_payment__kind",
        ).annotate(total=Sum("amount"), operations=Count("id"))
    )
    refunds_by_means = {str(row["means_of_payment_id"]): row for row in refunds}
    payments_by_means = {str(row["means_of_payment_id"]): row for row in payments}
    for means_id, refund in refunds_by_means.items():
        if means_id in payments_by_means:
            row = payments_by_means[means_id]
            row["gross_total"] = row["total"]
            row["refund_total"] = refund["total"]
            row["total"] -= refund["total"]
            row["refund_operations"] = refund["operations"]
        else:
            row = {
                **refund,
                "gross_total": Decimal("0.00"),
                "refund_total": refund["total"],
                "total": -refund["total"],
                "operations": 0,
                "refund_operations": refund["operations"],
            }
            payments.append(row)
            payments_by_means[means_id] = row
    for row in payments:
        row.setdefault("gross_total", row["total"])
        row.setdefault("refund_total", Decimal("0.00"))
        row.setdefault("refund_operations", 0)

    sales_payment_total = sum((row["total"] for row in payments), Decimal("0.00"))
    sales_cash_total = sum(
        (
            row["total"]
            for row in payments
            if row["means_of_payment__kind"] == MeansOfPayment.Kind.CASH
        ),
        Decimal("0.00"),
    )
    tender_movements = list(
        cash_session.cash_movements.exclude(means_of_payment__isnull=True)
        .values(
            "means_of_payment_id",
            "means_of_payment__name",
            "means_of_payment__kind",
            "movement_type",
        )
        .annotate(total=Sum("amount"), operations=Count("id"))
    )
    for movement in tender_movements:
        means_id = str(movement["means_of_payment_id"])
        direction = (
            Decimal("1.00")
            if movement["movement_type"] == CashMovement.MovementType.PAY_IN
            else Decimal("-1.00")
        )
        adjustment = movement["total"] * direction
        row = payments_by_means.get(means_id)
        if row is None:
            row = {
                "means_of_payment_id": movement["means_of_payment_id"],
                "means_of_payment__name": movement["means_of_payment__name"],
                "means_of_payment__kind": movement["means_of_payment__kind"],
                "total": Decimal("0.00"),
                "gross_total": Decimal("0.00"),
                "refund_total": Decimal("0.00"),
                "operations": 0,
                "refund_operations": 0,
            }
            payments.append(row)
            payments_by_means[means_id] = row
        row["total"] = (row["total"] + adjustment).quantize(MONEY_QUANTUM)
        row["operations"] += movement["operations"]

    movements = {
        row["movement_type"]: row
        for row in cash_session.cash_movements.values("movement_type")
        .annotate(total=Sum("amount"), operations=Count("id"))
    }
    payment_total = sales_payment_total
    refund_total = sum((row["total"] for row in refunds), Decimal("0.00"))
    cash_sales = sales_cash_total
    cash_totals = calculate_cash_session_totals(cash_session)
    transaction_counts = cash_session.transactions.aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status=PosTransaction.Status.COMPLETED)),
        cancelled=Count("id", filter=Q(status=PosTransaction.Status.CANCELLED)),
        pending=Count(
            "id",
            filter=Q(
                status__in=(
                    PosTransaction.Status.DRAFT,
                    PosTransaction.Status.PAYMENT_PENDING,
                    PosTransaction.Status.PROCESSING,
                )
            ),
        ),
        pending_invoices=Count(
            "id",
            filter=Q(
                billing_status__in=(
                    PosTransaction.BillingStatus.INVOICE_REQUESTED,
                    PosTransaction.BillingStatus.INVOICE_PROCESSING,
                    PosTransaction.BillingStatus.INVOICE_FAILED,
                )
            ),
        ),
    )
    declarations = {
        str(item.means_of_payment_id): item
        for item in cash_session.tender_declarations.select_related("means_of_payment")
    }
    for row in payments:
        declaration = declarations.get(str(row["means_of_payment_id"]))
        row["counted_amount"] = declaration.counted_amount if declaration else None
        row["difference"] = declaration.difference if declaration else None

    return {
        "opening_total": cash_session.opening_total.quantize(MONEY_QUANTUM),
        "payment_total": payment_total.quantize(MONEY_QUANTUM),
        "refund_total": refund_total.quantize(MONEY_QUANTUM),
        "cash_sales": cash_sales.quantize(MONEY_QUANTUM),
        "non_cash_sales": (payment_total - cash_sales).quantize(MONEY_QUANTUM),
        "cash_in": movements.get(CashMovement.MovementType.PAY_IN, {}).get(
            "total", Decimal("0.00")
        ),
        "cash_out": sum(
            (
                movements.get(movement_type, {}).get("total", Decimal("0.00"))
                for movement_type in (
                    CashMovement.MovementType.PAY_OUT,
                    CashMovement.MovementType.WITHDRAWAL,
                    CashMovement.MovementType.DEPOSIT,
                )
            ),
            Decimal("0.00"),
        ),
        "drawer_cash_in": cash_totals["cash_in"],
        "drawer_cash_out": cash_totals["cash_out"],
        "expected_cash_total": (
            cash_session.expected_cash_total
            if cash_session.expected_cash_total is not None
            else cash_totals["expected_cash_total"]
        ),
        "payments": payments,
        "movements": list(movements.values()),
        "transactions": transaction_counts,
        "can_close": not (
            transaction_counts["pending"] or transaction_counts["pending_invoices"]
        ),
    }


def get_pos_means_of_payment(*, company_id) -> QuerySet:
    return MeansOfPayment.objects.filter(
        company_id=company_id,
        active=True,
    ).order_by("kind", "name")


def get_pos_payment_methods(*, company_id) -> QuerySet:
    return PaymentMethod.objects.filter(
        company_id=company_id,
        active=True,
    ).order_by("is_credit", "name")


def get_pos_document_series(*, company_id, store_id) -> QuerySet:
    return DocumentSeries.objects.filter(
        company_id=company_id,
        store_id=store_id,
        document_type__code__in=("NV", "01", "03", "07", "08"),
        document_type__active=True,
        active=True,
    ).select_related("document_type").order_by("document_type__code", "series")


def get_invoiceable_tickets(
    *, company_id, store_id, customer_id=None, business_date=None,
) -> QuerySet:
    business_date = business_date or timezone.localdate()
    queryset = PosTransaction.objects.filter(
        company_id=company_id,
        store_id=store_id,
        status=PosTransaction.Status.COMPLETED,
        billing_status__in=(
            PosTransaction.BillingStatus.NOT_REQUESTED,
            PosTransaction.BillingStatus.INVOICE_REQUESTED,
            PosTransaction.BillingStatus.INVOICE_FAILED,
        ),
        sales_document__document_type__code="NV",
        sales_document__status="ISSUED",
        started_at__date=business_date,
    ).select_related(
        "sales_document__customer",
        "sales_document__document_type",
        "cash_session",
        "register",
        "cashier",
    ).prefetch_related("sales_document__pos_payments__means_of_payment")
    if customer_id:
        queryset = queryset.filter(sales_document__customer_id=customer_id)
    return queryset.order_by("started_at", "ticket_number")


def get_recent_pos_transactions(
    *, company_id, store_id, register_id=None, cash_session_id=None,
    business_date=None, limit=30,
) -> QuerySet:
    queryset = PosTransaction.objects.filter(
        company_id=company_id,
        store_id=store_id,
    ).filter(
        Q(status__in=(PosTransaction.Status.COMPLETED, PosTransaction.Status.CANCELLED))
        | Q(status=PosTransaction.Status.DRAFT, cash_session__status=CashSession.Status.OPEN)
    )
    if register_id:
        queryset = queryset.filter(register_id=register_id)
    if cash_session_id:
        queryset = queryset.filter(cash_session_id=cash_session_id)
    if business_date:
        queryset = queryset.filter(started_at__date=business_date)
    queryset = queryset.select_related(
        "sales_document__document_type",
        "sales_document__customer",
        "sales_document__store__company",
        "cash_session",
        "register",
        "cashier",
    ).prefetch_related(
        "sales_document__lines",
        "sales_document__pos_payments__means_of_payment",
    ).order_by("-completed_at", "-created_at")
    return queryset[:limit] if limit is not None else queryset


def get_credit_sales_with_balance(*, company_id, store_id, search="") -> QuerySet:
    money_field = DecimalField(max_digits=14, decimal_places=2)
    queryset = (
        PosTransaction.objects.filter(
            company_id=company_id,
            store_id=store_id,
            status=PosTransaction.Status.COMPLETED,
            payment_condition=PosTransaction.PaymentCondition.CREDIT,
        )
        .select_related("sales_document__customer", "sales_document__document_type", "cashier")
        .annotate(
            collected_total=Coalesce(
                Sum(
                    "sales_document__pos_payments__amount_in_sale_currency",
                    filter=Q(sales_document__pos_payments__status=SalesPayment.Status.REGISTERED),
                ),
                Value(Decimal("0.00"), output_field=money_field),
            )
        )
        .annotate(
            outstanding_total=ExpressionWrapper(
                F("sales_document__total") - F("collected_total"), output_field=money_field
            )
        )
        .filter(outstanding_total__gt=0)
    )
    search = (search or "").strip()
    if search:
        queryset = queryset.filter(
            Q(ticket_code__icontains=search)
            | Q(sales_document__series_code__icontains=search)
            | Q(sales_document__number__icontains=search)
            | Q(sales_document__customer_legal_name__icontains=search)
            | Q(sales_document__customer_document_number__icontains=search)
        )
    return queryset.order_by("sales_document__due_date", "started_at")


def get_daily_pos_sales_totals(*, company_id, store_id, business_date):
    """Gross completed POS sales grouped by physical register and currency."""
    return list(
        PosTransaction.objects.filter(
            company_id=company_id,
            store_id=store_id,
            status=PosTransaction.Status.COMPLETED,
            started_at__date=business_date,
        )
        .values("register_id", "register__code", "register__name", "sales_document__currency")
        .annotate(
            sessions=Count("cash_session_id", distinct=True),
            sales_count=Count("id"),
            sales_total=Sum("sales_document__total"),
        )
        .order_by("register__code", "sales_document__currency")
    )
