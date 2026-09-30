from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.utils import timezone
from uuid import UUID
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.db.models import Q, Sum

from apps.users.permissions import user_has_company_permission
from apps.companies.models import CompanyOperationalSettings
from apps.inventory.models import Product, Warehouse
from apps.partners.models import Customer
from apps.sales.models import DocumentSeries, MeansOfPayment
from apps.pos.forms import PosRegisterForm
from apps.pos.models import CashSafeMovement, CashSession, PosRegister, PosTransaction, SalesPayment
from apps.core.models import AuditLog
from apps.pos.selectors import (
    get_cash_session_history, get_cash_session_summary, get_daily_pos_sales_totals,
)


def _pos_context(request, permission_code):
    company_id = getattr(request, "active_company_id", None) or request.session.get("active_company_id")
    store_id = getattr(request, "active_store_id", None) or request.session.get("active_store_id")
    if not company_id or not store_id:
        return None, None, redirect("select_company")
    if not user_has_company_permission(request.user, company_id, permission_code, store_id):
        raise PermissionDenied("No tiene permiso para esta operación del POS.")
    return company_id, store_id, None


@login_required
def sale_workspace(request):
    """Render the POS shell; operational data is loaded from the versioned API."""
    company_id = getattr(request, "active_company_id", None)
    store_id = getattr(request, "active_store_id", None)
    if not company_id or not store_id:
        return redirect("select_company")
    if not user_has_company_permission(
        request.user,
        company_id,
        "read.pos",
        store_id,
    ):
        raise PermissionDenied("No tiene permiso para acceder al punto de venta.")
    operational_settings = CompanyOperationalSettings.objects.filter(
        company_id=company_id
    ).only("pos_product_search_mode").first()
    search_mode = (
        operational_settings.pos_product_search_mode
        if operational_settings
        else CompanyOperationalSettings.PosProductSearchMode.SEARCH
    )
    return render(request, "pos/sale.html", {"pos_product_search_mode": search_mode})


@login_required
def register_list(request):
    company_id, store_id, response = _pos_context(request, "manage.pos.configuration")
    if response:
        return response
    registers = PosRegister.objects.filter(
        company_id=company_id, store_id=store_id
    ).select_related(
        "default_warehouse", "default_price_list", "default_customer", "default_document_type"
    ).order_by("code")
    readiness = {
        "products": Product.objects.filter(company_id=company_id, active=True).count(),
        "warehouses": Warehouse.objects.filter(store_id=store_id, active=True).count(),
        "customers": Customer.objects.filter(company_id=company_id, active=True).count(),
        "series": DocumentSeries.objects.filter(
            company_id=company_id,
            store_id=store_id,
            active=True,
            document_type__code__in=("NV", "01", "03"),
        ).count(),
        "means": MeansOfPayment.objects.filter(company_id=company_id, active=True).count(),
    }
    readiness["ready"] = bool(registers and all(readiness.values()))
    return render(request, "pos/register_list.html", {
        "registers": registers,
        "readiness": readiness,
    })


@login_required
def transaction_list(request):
    company_id, store_id, response = _pos_context(request, "read.pos")
    if response:
        return response
    transactions = PosTransaction.objects.filter(
        company_id=company_id, store_id=store_id
    ).select_related(
        "register", "cash_session", "cashier", "sales_document__document_type"
    ).order_by("-started_at")
    register_id = request.GET.get("register", "")
    session_id = request.GET.get("session", "")
    status = request.GET.get("status", "")
    if register_id:
        transactions = transactions.filter(register_id=register_id)
    if session_id:
        transactions = transactions.filter(cash_session_id=session_id)
    if status:
        transactions = transactions.filter(status=status)
    page_obj = Paginator(transactions, 80).get_page(request.GET.get("page"))
    return render(request, "pos/transaction_list.html", {
        "page_obj": page_obj,
        "registers": PosRegister.objects.filter(company_id=company_id, store_id=store_id),
        "selected_register": register_id,
        "selected_session": session_id,
        "selected_status": status,
        "status_choices": PosTransaction.Status.choices,
    })


def _cash_session_access(request):
    company_id, store_id, response = _pos_context(request, "read.pos.cash_sessions")
    if response:
        return company_id, store_id, response, False
    can_audit_all = user_has_company_permission(
        request.user, company_id, "read.pos.cash_sessions_all", store_id
    )
    return company_id, store_id, None, can_audit_all


@login_required
def cash_session_list(request):
    company_id, store_id, response, can_audit_all = _cash_session_access(request)
    if response:
        return response
    sessions = get_cash_session_history(company_id=company_id, store_id=store_id)
    if not can_audit_all:
        sessions = sessions.filter(opened_by=request.user)

    selected_register = request.GET.get("register", "")
    selected_cashier = request.GET.get("cashier", "")
    selected_status = request.GET.get("status", "")
    requested_daily_date = parse_date(request.GET.get("daily_date", ""))
    date_from = parse_date(request.GET.get("date_from", ""))
    date_to = parse_date(request.GET.get("date_to", ""))
    # The daily summary and the closure list must always describe the same day.
    if requested_daily_date:
        date_from = requested_daily_date
        date_to = requested_daily_date
    try:
        selected_register_uuid = UUID(selected_register) if selected_register else None
    except (TypeError, ValueError):
        selected_register_uuid = None
        selected_register = ""
    try:
        selected_cashier_uuid = UUID(selected_cashier) if selected_cashier else None
    except (TypeError, ValueError):
        selected_cashier_uuid = None
        selected_cashier = ""
    if selected_register_uuid:
        sessions = sessions.filter(register_id=selected_register)
    if selected_cashier_uuid and can_audit_all:
        sessions = sessions.filter(opened_by_id=selected_cashier)
    if selected_status in dict(CashSession.Status.choices):
        sessions = sessions.filter(status=selected_status)
    if date_from:
        sessions = sessions.filter(opened_at__date__gte=date_from)
    if date_to:
        sessions = sessions.filter(opened_at__date__lte=date_to)

    page_obj = Paginator(sessions, 50).get_page(request.GET.get("page"))
    for item in page_obj.object_list:
        item.display_expected_cash_total = (
            item.expected_cash_total
            if item.expected_cash_total is not None
            else get_cash_session_summary(item)["expected_cash_total"]
        )
    query = request.GET.copy()
    query.pop("page", None)
    cashiers = []
    daily_date = requested_daily_date or date_from or timezone.localdate()
    daily_totals = []
    if can_audit_all:
        cashiers = (
            CashSession.objects.filter(company_id=company_id, store_id=store_id)
            .exclude(opened_by=None)
            .values("opened_by_id", "opened_by__name", "opened_by__email")
            .distinct()
            .order_by("opened_by__name", "opened_by__email")
        )
        daily_totals = get_daily_pos_sales_totals(
            company_id=company_id, store_id=store_id, business_date=daily_date
        )
    return render(request, "pos/cash_session_list.html", {
        "page_obj": page_obj,
        "registers": PosRegister.objects.filter(company_id=company_id, store_id=store_id),
        "cashiers": cashiers,
        "status_choices": CashSession.Status.choices,
        "selected_register": selected_register,
        "selected_cashier": selected_cashier,
        "selected_status": selected_status,
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "pagination_query": query.urlencode(),
        "can_audit_all": can_audit_all,
        "can_manage_safe": user_has_company_permission(
            request.user, company_id, "manage.pos.cash_safe", store_id
        ),
        "daily_date": daily_date.isoformat(),
        "daily_totals": daily_totals,
    })


@login_required
def cash_session_detail(request, pk):
    company_id, store_id, response, can_audit_all = _cash_session_access(request)
    if response:
        return response
    sessions = CashSession.objects.filter(company_id=company_id, store_id=store_id)
    if not can_audit_all:
        sessions = sessions.filter(opened_by=request.user)
    cash_session = get_object_or_404(
        sessions.select_related(
            "register", "store", "opened_by", "closed_by", "difference_authorized_by"
        ),
        pk=pk,
    )
    summary = get_cash_session_summary(cash_session)
    sales = cash_session.transactions.select_related(
        "sales_document__customer", "sales_document__document_type", "cashier"
    ).order_by("-started_at")
    movements = cash_session.cash_movements.select_related(
        "created_by", "authorized_by"
    ).order_by("-created_at")
    payments = cash_session.sales_payments.filter(
        status=SalesPayment.Status.REGISTERED
    ).select_related(
        "sales_document__customer", "means_of_payment", "created_by"
    ).order_by("-paid_at")
    return render(request, "pos/cash_session_detail.html", {
        "cash_session": cash_session,
        "summary": summary,
        "sales": sales,
        "movements": movements,
        "payments": payments,
    })


@login_required
def cash_safe_ledger(request):
    company_id, store_id, response = _pos_context(request, "manage.pos.cash_safe")
    if response:
        return response
    movements = CashSafeMovement.objects.filter(
        company_id=company_id, store_id=store_id
    ).select_related("cash_session", "created_by", "authorized_by")

    if request.method == "POST":
        try:
            amount = Decimal(request.POST.get("amount", "0")).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError):
            amount = Decimal("0.00")
        currency = request.POST.get("currency", "PEN")
        movement_type = request.POST.get("movement_type", "")
        recipient = request.POST.get("recipient_name", "").strip()
        destination = request.POST.get("destination", "").strip()
        reference = request.POST.get("reference", "").strip()
        notes = request.POST.get("notes", "").strip()
        allowed_types = {
            CashSafeMovement.MovementType.BANK_DEPOSIT,
            CashSafeMovement.MovementType.OWNER_HANDOVER,
            CashSafeMovement.MovementType.CASH_PAYMENT,
            CashSafeMovement.MovementType.DRAWER_TRANSFER,
        }
        balance = movements.filter(currency=currency).aggregate(
            incoming=Sum("amount", filter=Q(direction=CashSafeMovement.Direction.IN)),
            outgoing=Sum("amount", filter=Q(direction=CashSafeMovement.Direction.OUT)),
        )
        available = (balance["incoming"] or Decimal("0")) - (balance["outgoing"] or Decimal("0"))
        if movement_type not in allowed_types:
            messages.error(request, "Seleccione un motivo válido para la salida.")
        elif amount <= 0:
            messages.error(request, "El importe debe ser mayor que cero.")
        elif amount > available:
            messages.error(request, f"El saldo disponible en caja fuerte es {currency} {available:.2f}.")
        elif not recipient:
            messages.error(request, "Indique quién recibe o retira el dinero.")
        elif movement_type == CashSafeMovement.MovementType.BANK_DEPOSIT and not destination:
            messages.error(request, "Indique el banco o cuenta de destino.")
        else:
            with transaction.atomic():
                movement = CashSafeMovement.objects.create(
                    company_id=company_id, store_id=store_id,
                    direction=CashSafeMovement.Direction.OUT,
                    movement_type=movement_type, amount=amount, currency=currency,
                    recipient_name=recipient, destination=destination,
                    reference=reference, notes=notes,
                    created_by=request.user, authorized_by=request.user,
                )
                AuditLog.objects.create(
                    user=request.user, action="CASH_SAFE_OUT",
                    entity="CashSafeMovement", entity_id=str(movement.pk),
                    meta_data={
                        "amount": str(amount), "currency": currency,
                        "recipient": recipient, "destination": destination,
                        "movement_type": movement_type,
                    },
                )
            messages.success(request, "Salida de caja fuerte registrada correctamente.")
            return redirect("pos:cash_safe_ledger")

    balances = []
    for currency in ("PEN", "USD"):
        totals = movements.filter(currency=currency).aggregate(
            incoming=Sum("amount", filter=Q(direction=CashSafeMovement.Direction.IN)),
            outgoing=Sum("amount", filter=Q(direction=CashSafeMovement.Direction.OUT)),
        )
        incoming = totals["incoming"] or Decimal("0.00")
        outgoing = totals["outgoing"] or Decimal("0.00")
        balances.append({"currency": currency, "incoming": incoming, "outgoing": outgoing, "balance": incoming - outgoing})
    return render(request, "pos/cash_safe_ledger.html", {
        "movements": movements[:200], "balances": balances,
        "movement_types": [
            choice for choice in CashSafeMovement.MovementType.choices
            if choice[0] != CashSafeMovement.MovementType.CLOSING_DEPOSIT
            and choice[0] != CashSafeMovement.MovementType.ADJUSTMENT
        ],
    })


@login_required
def register_create(request):
    company_id, store_id, response = _pos_context(request, "manage.pos.configuration")
    if response:
        return response
    form = PosRegisterForm(
        request.POST or None, company_id=company_id, store_id=store_id
    )
    if request.method == "POST" and form.is_valid():
        register = form.save()
        messages.success(request, f"Caja {register.code} configurada correctamente.")
        return redirect("pos:register_list")
    return render(request, "pos/register_form.html", {"form": form, "title": "Nueva caja POS"})


@login_required
def register_update(request, pk):
    company_id, store_id, response = _pos_context(request, "manage.pos.configuration")
    if response:
        return response
    register = get_object_or_404(
        PosRegister, pk=pk, company_id=company_id, store_id=store_id
    )
    form = PosRegisterForm(
        request.POST or None,
        instance=register,
        company_id=company_id,
        store_id=store_id,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Caja {register.code} actualizada correctamente.")
        return redirect("pos:register_list")
    return render(request, "pos/register_form.html", {"form": form, "title": "Editar caja POS"})


@login_required
def receipt_a4(request, transaction_id):
    """Vista A4 imprimible del comprobante POS, limitada al contexto activo."""
    company_id = getattr(request, "active_company_id", None) or request.session.get("active_company_id")
    store_id = getattr(request, "active_store_id", None) or request.session.get("active_store_id")
    if not user_has_company_permission(
        request.user, company_id, "read.pos", store_id
    ):
        raise PermissionDenied("No tiene permiso para consultar comprobantes del POS.")
    transaction = get_object_or_404(
        PosTransaction.objects.select_related(
            "sales_document__store__company",
            "sales_document__document_type",
        ).prefetch_related("sales_document__lines"),
        pk=transaction_id,
        company_id=company_id,
        store_id=store_id,
    )
    sales_document = transaction.sales_document
    company = sales_document.store.company if sales_document.store_id else None
    return render(
        request,
        "sales/pdf/document_pdf.html",
        {"sales_document": sales_document, "company": company, "from_pos": True},
    )
