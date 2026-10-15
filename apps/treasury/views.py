import csv
from decimal import Decimal
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.urls import reverse

from apps.users.permissions import (
    user_has_company_permission,
    user_is_company_admin,
    user_store_role,
)
from apps.companies.models import Company, Store

from .forms import (
    BankAccountForm,
    BankMovementForm,
    BankStatementImportForm,
    CashSafeCountForm,
    CashSafeDepositConfirmationForm,
    CashSafeAttachmentForm,
    CashSafeIncomeForm,
    CashSafeWithdrawalForm,
    TreasuryFundForm,
)
from .models import (
    BankAccount, BankMovement, BankStatement, CashSafeCount, CashSafeDeposit,
    CashSafeMovement, CashSafeMovementAttachment, TreasuryFund,
)
from .selectors import get_cash_safe_balances, get_cash_safe_report_movements
from .services import TreasuryDomainError, register_cash_safe_withdrawal
from .services import (
    approve_cash_safe_movement,
    add_cash_safe_attachment,
    reject_cash_safe_movement,
    reverse_cash_safe_movement,
    bank_account_balance,
    bank_account_balance_at,
    close_bank_statement,
    confirm_cash_safe_deposit,
    import_bank_statement,
    match_bank_statement_line,
    register_bank_movement,
    reverse_bank_movement,
    register_cash_safe_income,
    register_cash_safe_count,
    review_cash_safe_count,
    unmatch_bank_statement_line,
    get_or_create_default_fund,
)


def _treasury_context(request, permission_code):
    company_id = getattr(request, "active_company_id", None) or request.session.get("active_company_id")
    store_id = getattr(request, "active_store_id", None) or request.session.get("active_store_id")
    if not company_id or not store_id:
        return None, None, redirect("select_company")
    if not user_has_company_permission(request.user, company_id, permission_code, store_id):
        raise PermissionDenied("No tiene permiso para esta operación de Tesorería.")
    return company_id, store_id, None


def _valid_fund_id(value, *, company_id, store_id, active_only=False):
    try:
        fund_id = UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return ""
    funds = TreasuryFund.objects.filter(
        pk=fund_id, company_id=company_id, store_id=store_id
    )
    if active_only:
        funds = funds.filter(active=True)
    return str(fund_id) if funds.exists() else ""


def _bank_account_settings_context(request):
    company_id = getattr(request, "active_company_id", None) or request.session.get(
        "active_company_id"
    )
    if not company_id:
        return None, redirect("select_company")
    if not request.user.is_superuser and not user_is_company_admin(request.user, company_id):
        raise PermissionDenied("Solo un administrador puede configurar cuentas bancarias.")
    return company_id, None


@login_required
def treasury_fund_list(request):
    company_id, store_id, response = _treasury_context(
        request, "manage.treasury.cash_safe"
    )
    if response:
        return response
    can_manage_funds = request.user.is_superuser or user_is_company_admin(
        request.user, company_id
    )
    if request.method == "POST" and not can_manage_funds:
        raise PermissionDenied("Solo un administrador puede configurar fondos de efectivo.")
    get_or_create_default_fund(company_id=company_id, store_id=store_id)
    editing = None
    edit_id = request.GET.get("edit")
    if edit_id and can_manage_funds:
        editing = get_object_or_404(
            TreasuryFund, pk=edit_id, company_id=company_id, store_id=store_id
        )
    action = request.POST.get("action", "save") if request.method == "POST" else "save"
    if request.method == "POST" and action in {"set_default", "toggle"}:
        fund = get_object_or_404(
            TreasuryFund, pk=request.POST.get("fund_id"),
            company_id=company_id, store_id=store_id,
        )
        if action == "set_default":
            with transaction.atomic():
                TreasuryFund.objects.filter(store_id=store_id, is_default=True).update(
                    is_default=False
                )
                fund.is_default = True
                fund.active = True
                fund.save(update_fields=("is_default", "active", "updated_at"))
            messages.success(request, f"{fund.name} ahora es el fondo principal.")
        elif fund.is_default:
            messages.error(request, "El fondo principal no puede desactivarse.")
        else:
            fund.active = not fund.active
            fund.save(update_fields=("active", "updated_at"))
            messages.success(request, "Estado del fondo actualizado.")
        return redirect("treasury:treasury_fund_list")
    if request.method == "POST" and action == "save":
        editing_id = request.POST.get("fund_id")
        if editing_id:
            editing = get_object_or_404(
                TreasuryFund, pk=editing_id, company_id=company_id, store_id=store_id
            )
        form = TreasuryFundForm(
            request.POST, instance=editing, company_id=company_id, store_id=store_id
        )
        if form.is_valid():
            fund = form.save(commit=False)
            fund.company_id = company_id
            fund.store_id = store_id
            fund.full_clean()
            fund.save()
            messages.success(request, "Fondo de efectivo guardado correctamente.")
            return redirect("treasury:treasury_fund_list")
    else:
        form = TreasuryFundForm(
            instance=editing, company_id=company_id, store_id=store_id
        )
    funds = TreasuryFund.objects.filter(
        company_id=company_id, store_id=store_id
    ).annotate(movement_count=Count("cash_movements"))
    for fund in funds:
        fund.balances = get_cash_safe_balances(fund.cash_movements.all())
    return render(request, "treasury/treasury_fund_list.html", {
        "form": form, "funds": funds, "editing": editing,
        "can_manage_funds": can_manage_funds,
    })


@login_required
def cash_safe_ledger(request):
    company_id, store_id, response = _treasury_context(request, "manage.treasury.cash_safe")
    if response:
        return response
    get_or_create_default_fund(company_id=company_id, store_id=store_id)
    funds = TreasuryFund.objects.filter(
        company_id=company_id, store_id=store_id, active=True
    ).order_by("name")
    base_movements = CashSafeMovement.objects.filter(
        company_id=company_id, store_id=store_id
    ).select_related(
        "fund", "destination_fund", "destination_register", "transfer_source", "cash_session",
        "created_by", "authorized_by", "deposit_tracking"
    )
    action = request.POST.get("action", "request") if request.method == "POST" else "request"
    can_authorize = user_has_company_permission(
        request.user, company_id, "authorize.treasury.cash_safe", store_id
    )
    can_self_authorize = user_store_role(request.user, company_id, store_id) == "ADMIN"
    withdrawal_form = CashSafeWithdrawalForm(
        request.POST if request.method == "POST" and action == "request" else None,
        request.FILES if request.method == "POST" and action == "request" else None,
        company_id=company_id, store_id=store_id,
    )
    if request.method == "POST" and action in {"approve", "reject", "reverse"}:
        if not can_authorize:
            raise PermissionDenied("No tiene permiso para autorizar movimientos de Tesorería.")
        movement_id = request.POST.get("movement_id")
        reason = request.POST.get("reason", "").strip()
        try:
            if action == "approve":
                approve_cash_safe_movement(
                    movement_id=movement_id, company_id=company_id,
                    store_id=store_id, user=request.user,
                )
                messages.success(request, "Movimiento aprobado y aplicado al saldo.")
            elif action == "reject":
                if not reason:
                    raise TreasuryDomainError("Indique el motivo del rechazo.")
                reject_cash_safe_movement(
                    movement_id=movement_id, company_id=company_id,
                    store_id=store_id, reason=reason, user=request.user,
                )
                messages.success(request, "Solicitud rechazada.")
            else:
                if not reason:
                    raise TreasuryDomainError("Indique el motivo de la reversión.")
                reverse_cash_safe_movement(
                    movement_id=movement_id, company_id=company_id,
                    store_id=store_id, reason=reason, user=request.user,
                )
                messages.success(request, "Movimiento revertido con trazabilidad.")
        except (TreasuryDomainError, CashSafeMovement.DoesNotExist, ValidationError) as exc:
            messages.error(request, str(exc) or "El movimiento solicitado no existe.")
        return redirect("treasury:cash_safe_ledger")
    if request.method == "POST" and action == "request" and withdrawal_form.is_valid():
        try:
            register_cash_safe_withdrawal(
                company_id=company_id, store_id=store_id, user=request.user,
                **withdrawal_form.cleaned_data,
            )
        except TreasuryDomainError as exc:
            withdrawal_form.add_error("amount", str(exc))
        else:
            messages.success(request, "Solicitud de salida registrada para aprobación.")
            return redirect("treasury:cash_safe_ledger")

    movements = base_movements
    date_from = parse_date(request.GET.get("date_from", ""))
    date_to = parse_date(request.GET.get("date_to", ""))
    selected_currency = request.GET.get("currency", "")
    selected_direction = request.GET.get("direction", "")
    selected_type = request.GET.get("movement_type", "")
    selected_fund = request.GET.get("fund", "")
    search = request.GET.get("q", "").strip()
    if date_from:
        movements = movements.filter(created_at__date__gte=date_from)
    if date_to:
        movements = movements.filter(created_at__date__lte=date_to)
    if selected_currency in {"PEN", "USD"}:
        movements = movements.filter(currency=selected_currency)
    else:
        selected_currency = ""
    if selected_direction in dict(CashSafeMovement.Direction.choices):
        movements = movements.filter(direction=selected_direction)
    else:
        selected_direction = ""
    if selected_type in dict(CashSafeMovement.MovementType.choices):
        movements = movements.filter(movement_type=selected_type)
    else:
        selected_type = ""
    selected_fund = _valid_fund_id(
        selected_fund, company_id=company_id, store_id=store_id, active_only=True
    )
    if selected_fund:
        movements = movements.filter(fund_id=selected_fund)
    balance_movements = (
        base_movements.filter(fund_id=selected_fund) if selected_fund else base_movements
    )
    if search:
        movements = movements.filter(
            Q(recipient_name__icontains=search) | Q(destination__icontains=search)
            | Q(reference__icontains=search) | Q(notes__icontains=search)
        )
    effective_movements = movements.filter(
        status__in=(CashSafeMovement.Status.POSTED, CashSafeMovement.Status.REVERSED)
    )
    filtered_totals = effective_movements.aggregate(
        incoming=Sum("amount", filter=Q(direction=CashSafeMovement.Direction.IN)),
        outgoing=Sum("amount", filter=Q(direction=CashSafeMovement.Direction.OUT)),
    )
    page_obj = Paginator(movements, 50).get_page(request.GET.get("page"))
    running = {"PEN": Decimal("0.00"), "USD": Decimal("0.00")}
    running_by_id = {}
    for ledger_item in balance_movements.filter(
        status__in=(CashSafeMovement.Status.POSTED, CashSafeMovement.Status.REVERSED)
    ).order_by("created_at", "id"):
        direction = Decimal("1") if ledger_item.direction == CashSafeMovement.Direction.IN else Decimal("-1")
        running[ledger_item.currency] += direction * ledger_item.amount
        running_by_id[ledger_item.pk] = running[ledger_item.currency]
    for ledger_item in page_obj.object_list:
        ledger_item.running_balance = running_by_id.get(ledger_item.pk)
    query = request.GET.copy()
    query.pop("page", None)
    today_totals = balance_movements.filter(
        created_at__date=timezone.localdate(),
        status__in=(CashSafeMovement.Status.POSTED, CashSafeMovement.Status.REVERSED),
    ).aggregate(
        incoming=Sum("amount", filter=Q(direction=CashSafeMovement.Direction.IN)),
        outgoing=Sum("amount", filter=Q(direction=CashSafeMovement.Direction.OUT)),
    )
    pending_approval_count = base_movements.filter(
        status=CashSafeMovement.Status.PENDING
    ).count()
    in_transit_count = CashSafeDeposit.objects.filter(
        cash_movement__company_id=company_id,
        cash_movement__store_id=store_id,
        status=CashSafeDeposit.Status.IN_TRANSIT,
    ).count()
    pending_count_count = CashSafeCount.objects.filter(
        company_id=company_id, store_id=store_id,
        status=CashSafeCount.Status.PENDING,
    ).count()
    last_closed_count = CashSafeCount.objects.filter(
        company_id=company_id, store_id=store_id,
        status=CashSafeCount.Status.CLOSED,
    ).select_related("fund").order_by("-counted_at").first()
    current_month = timezone.localdate().replace(day=1)
    fund_balance_data = {}
    overdue_count_count = 0
    for fund in funds:
        for balance in get_cash_safe_balances(base_movements.filter(fund=fund)):
            fund_balance_data[f"{fund.pk}:{balance['currency']}"] = str(balance["balance"])
            if balance["currency"] == "PEN" or balance["balance"]:
                has_current_count = CashSafeCount.objects.filter(
                    company_id=company_id, store_id=store_id, fund=fund,
                    currency=balance["currency"], status=CashSafeCount.Status.CLOSED,
                    counted_at__date__gte=current_month,
                ).exists()
                overdue_count_count += 0 if has_current_count else 1
    count_overdue = overdue_count_count > 0
    return render(request, "treasury/cash_safe_ledger.html", {
        "withdrawal_form": withdrawal_form,
        "can_authorize_safe": can_authorize,
        "can_self_authorize_safe": can_self_authorize,
        "page_obj": page_obj, "movements": page_obj.object_list,
        "balances": get_cash_safe_balances(balance_movements),
        "last_movement": balance_movements.first(),
        "today_incoming": today_totals["incoming"] or Decimal("0.00"),
        "today_outgoing": today_totals["outgoing"] or Decimal("0.00"),
        "filtered_incoming": filtered_totals["incoming"] or Decimal("0.00"),
        "filtered_outgoing": filtered_totals["outgoing"] or Decimal("0.00"),
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "selected_currency": selected_currency, "selected_direction": selected_direction,
        "selected_type": selected_type, "search": search,
        "funds": funds, "selected_fund": selected_fund,
        "direction_choices": CashSafeMovement.Direction.choices,
        "all_movement_types": CashSafeMovement.MovementType.choices,
        "pagination_query": query.urlencode(),
        "form_data": request.POST if request.method == "POST" else {},
        "movement_types": withdrawal_form.fields["movement_type"].choices,
        "pending_approval_count": pending_approval_count,
        "in_transit_count": in_transit_count,
        "pending_count_count": pending_count_count,
        "last_closed_count": last_closed_count,
        "count_overdue": count_overdue,
        "overdue_count_count": overdue_count_count,
        "fund_balance_data": fund_balance_data,
    })


@login_required
def cash_safe_income_create(request):
    company_id, store_id, response = _treasury_context(
        request, "manage.treasury.cash_safe"
    )
    if response:
        return response
    get_or_create_default_fund(company_id=company_id, store_id=store_id)
    form = CashSafeIncomeForm(
        request.POST or None, company_id=company_id, store_id=store_id
    )
    if request.method == "POST" and form.is_valid():
        register_cash_safe_income(
            company_id=company_id, store_id=store_id, user=request.user,
            **form.cleaned_data,
        )
        messages.success(request, "Ingreso registrado y enviado a revisión.")
        return redirect("treasury:cash_safe_ledger")
    balances = get_cash_safe_balances(CashSafeMovement.objects.filter(
        company_id=company_id, store_id=store_id
    ))
    return render(request, "treasury/cash_safe_income_form.html", {
        "form": form, "balances": balances,
    })


@login_required
def cash_safe_movement_detail(request, pk):
    company_id, store_id, response = _treasury_context(
        request, "manage.treasury.cash_safe"
    )
    if response:
        return response
    movement = get_object_or_404(
        CashSafeMovement.objects.select_related(
            "store", "fund", "destination_fund", "destination_register", "transfer_source",
            "created_by", "authorized_by", "cash_session",
            "bank_account__bank", "reversed_movement", "supplier",
            "purchase_document", "expense_category",
        ), pk=pk, company_id=company_id, store_id=store_id,
    )
    attachment_form = CashSafeAttachmentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and attachment_form.is_valid():
        add_cash_safe_attachment(
            movement=movement, uploaded_file=attachment_form.cleaned_data["file"],
            user=request.user,
        )
        messages.success(request, "Comprobante adjuntado correctamente.")
        return redirect("treasury:cash_safe_movement_detail", pk=movement.pk)
    try:
        deposit_tracking = movement.deposit_tracking
    except CashSafeDeposit.DoesNotExist:
        deposit_tracking = None
    try:
        bank_movement = movement.bank_movement
    except BankMovement.DoesNotExist:
        bank_movement = None
    return render(request, "treasury/cash_safe_movement_detail.html", {
        "movement": movement, "deposit_tracking": deposit_tracking,
        "bank_movement": bank_movement, "attachment_form": attachment_form,
        "attachments": movement.attachments.select_related("uploaded_by"),
    })


@login_required
def cash_safe_attachment_download(request, pk):
    company_id, store_id, response = _treasury_context(
        request, "manage.treasury.cash_safe"
    )
    if response:
        return response
    attachment = get_object_or_404(
        CashSafeMovementAttachment.objects.select_related("movement"),
        pk=pk, movement__company_id=company_id, movement__store_id=store_id,
    )
    attachment.file.open("rb")
    return FileResponse(
        attachment.file, as_attachment=True,
        filename=attachment.original_name, content_type=attachment.content_type,
    )


def _csv_safe(value):
    text = str(value or "")
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


@login_required
def cash_safe_export(request):
    company_id, store_id, response = _treasury_context(
        request, "manage.treasury.cash_safe"
    )
    if response:
        return response
    movements = CashSafeMovement.objects.filter(
        company_id=company_id, store_id=store_id
    ).select_related(
        "fund", "destination_register", "created_by", "authorized_by", "supplier",
        "purchase_document", "expense_category",
    ).order_by("created_at", "id")
    date_from = parse_date(request.GET.get("date_from", ""))
    date_to = parse_date(request.GET.get("date_to", ""))
    currency = request.GET.get("currency", "")
    direction = request.GET.get("direction", "")
    movement_type = request.GET.get("movement_type", "")
    fund_id = request.GET.get("fund", "")
    search = request.GET.get("q", "").strip()
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
    fund_id = _valid_fund_id(fund_id, company_id=company_id, store_id=store_id)
    if fund_id:
        movements = movements.filter(
            fund_id=fund_id, fund__company_id=company_id, fund__store_id=store_id
        )
    if search:
        movements = movements.filter(
            Q(recipient_name__icontains=search) | Q(destination__icontains=search)
            | Q(reference__icontains=search) | Q(notes__icontains=search)
        )
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="libro_caja_fuerte.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow([
        "Fecha", "Documento", "Fondo", "Tipo", "Estado", "Moneda", "Entrada", "Salida",
        "Entregado por/a", "Destino", "Referencia", "Registrado por",
        "Autorizado por", "Fecha autorización", "Observación",
        "Proveedor", "Documento de compra", "Categoría", "N.º comprobante",
    ])
    for item in movements:
        writer.writerow([
            timezone.localtime(item.created_at).strftime("%d/%m/%Y %H:%M"),
            item.movement_number, item.fund.name, item.get_movement_type_display(), item.get_status_display(),
            item.currency, item.amount if item.direction == "IN" else "",
            item.amount if item.direction == "OUT" else "",
            _csv_safe(item.recipient_name), _csv_safe(item.destination),
            _csv_safe(item.reference), item.created_by.display_name if item.created_by else "Sistema",
            item.authorized_by.display_name if item.authorized_by else "",
            timezone.localtime(item.authorized_at).strftime("%d/%m/%Y %H:%M") if item.authorized_at else "",
            _csv_safe(item.notes),
            _csv_safe(item.supplier), _csv_safe(item.purchase_document),
            _csv_safe(item.expense_category), _csv_safe(item.supporting_document_number),
        ])
    return response


@login_required
def cash_safe_export_xlsx(request):
    company_id, store_id, response = _treasury_context(
        request, "manage.treasury.cash_safe"
    )
    if response:
        return response
    date_from = parse_date(request.GET.get("date_from", ""))
    date_to = parse_date(request.GET.get("date_to", ""))
    if date_from and date_to and date_to < date_from:
        return HttpResponse("El rango de fechas no es válido.", status=400)
    fund_id = _valid_fund_id(
        request.GET.get("fund", ""), company_id=company_id, store_id=store_id
    )
    movements = get_cash_safe_report_movements(
        company_id=company_id, store_id=store_id,
        date_from=date_from, date_to=date_to,
        currency=request.GET.get("currency", ""),
        direction=request.GET.get("direction", ""),
        movement_type=request.GET.get("movement_type", ""),
        fund_id=fund_id, search=request.GET.get("q", "").strip(),
    )
    from .reports import build_cash_safe_report

    content = build_cash_safe_report(
        movements,
        store_name=Store.objects.get(pk=store_id, company_id=company_id).name,
        date_from=date_from, date_to=date_to,
    )
    filename = "reporte_caja_fuerte"
    if date_from or date_to:
        filename += f"_{date_from or 'inicio'}_{date_to or 'actual'}"
    export = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    export["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
    return export


@login_required
def cash_safe_count_list(request):
    company_id, store_id, response = _treasury_context(
        request, "manage.treasury.cash_safe"
    )
    if response:
        return response
    can_review = user_has_company_permission(
        request.user, company_id, "authorize.treasury.cash_safe", store_id
    )
    can_self_review = user_store_role(request.user, company_id, store_id) == "ADMIN"
    get_or_create_default_fund(company_id=company_id, store_id=store_id)
    funds = TreasuryFund.objects.filter(
        company_id=company_id, store_id=store_id, active=True
    ).order_by("name")
    form = CashSafeCountForm(
        request.POST or None, initial={"counted_at": timezone.localtime()},
        company_id=company_id, store_id=store_id,
    )
    action = request.POST.get("action", "create") if request.method == "POST" else "create"
    if request.method == "POST" and action in {"close", "reject"}:
        if not can_review:
            raise PermissionDenied("No tiene permiso para revisar arqueos.")
        try:
            review_cash_safe_count(
                count_id=request.POST.get("count_id"), company_id=company_id,
                store_id=store_id, action=action,
                review_notes=request.POST.get("review_notes", "").strip(), user=request.user,
            )
            messages.success(
                request, "Arqueo cerrado y diferencia ajustada."
                if action == "close" else "Arqueo rechazado."
            )
        except (TreasuryDomainError, CashSafeCount.DoesNotExist, ValidationError) as exc:
            messages.error(request, str(exc) or "No se encontró el arqueo solicitado.")
        return redirect("treasury:cash_safe_count_list")
    if request.method == "POST" and action == "create" and form.is_valid():
        try:
            register_cash_safe_count(
                company_id=company_id, store_id=store_id, user=request.user,
                **form.cleaned_data,
            )
        except TreasuryDomainError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Arqueo registrado y enviado a revisión.")
            return redirect("treasury:cash_safe_count_list")
    counts = CashSafeCount.objects.filter(
        company_id=company_id, store_id=store_id
    ).select_related("fund", "counted_by", "reviewed_by", "adjustment_movement")
    last_closed = counts.filter(status=CashSafeCount.Status.CLOSED).first()
    selected_status = request.GET.get("status", "")
    selected_currency = request.GET.get("currency", "")
    selected_fund = request.GET.get("fund", "")
    if selected_status in dict(CashSafeCount.Status.choices):
        counts = counts.filter(status=selected_status)
    else:
        selected_status = ""
    if selected_currency in {"PEN", "USD"}:
        counts = counts.filter(currency=selected_currency)
    else:
        selected_currency = ""
    selected_fund = _valid_fund_id(
        selected_fund, company_id=company_id, store_id=store_id, active_only=True
    )
    if selected_fund:
        counts = counts.filter(fund_id=selected_fund)
    page_obj = Paginator(counts, 30).get_page(request.GET.get("page"))
    safe_movements = CashSafeMovement.objects.filter(
        company_id=company_id, store_id=store_id
    )
    fund_balances = []
    for fund in funds:
        for balance in get_cash_safe_balances(safe_movements.filter(fund=fund)):
            fund_balances.append({"fund": fund, **balance})
    return render(request, "treasury/cash_safe_count_list.html", {
        "form": form, "page_obj": page_obj, "counts": page_obj.object_list,
        "status_choices": CashSafeCount.Status.choices,
        "selected_status": selected_status, "selected_currency": selected_currency,
        "funds": funds, "selected_fund": selected_fund,
        "can_review": can_review, "can_self_review": can_self_review,
        "last_closed": last_closed,
        "safe_balances": get_cash_safe_balances(safe_movements),
        "fund_balances": fund_balances,
    })


@login_required
def cash_safe_count_detail(request, pk):
    company_id, store_id, response = _treasury_context(request, "manage.treasury.cash_safe")
    if response:
        return response
    count = get_object_or_404(
        CashSafeCount.objects.select_related(
            "store", "fund", "counted_by", "reviewed_by", "adjustment_movement"
        ), pk=pk, company_id=company_id, store_id=store_id,
    )
    denomination_rows = []
    for denomination, quantity in (count.denominations or {}).items():
        try:
            denomination_value = Decimal(str(denomination))
            quantity_value = int(quantity)
        except (ValueError, TypeError):
            continue
        denomination_rows.append({
            "denomination": denomination_value, "quantity": quantity_value,
            "total": denomination_value * quantity_value,
        })
    denomination_rows.sort(key=lambda row: row["denomination"], reverse=True)
    previous_count = CashSafeCount.objects.filter(
        company_id=company_id, store_id=store_id, currency=count.currency,
        fund=count.fund,
        status=CashSafeCount.Status.CLOSED, counted_at__lt=count.counted_at,
    ).order_by("-counted_at", "-created_at").first()
    period_movements = CashSafeMovement.objects.filter(
        company_id=company_id, store_id=store_id, currency=count.currency,
        fund=count.fund,
        status__in=(CashSafeMovement.Status.POSTED, CashSafeMovement.Status.REVERSED),
        created_at__lte=count.counted_at,
    ).select_related("created_by", "authorized_by", "cash_session")
    if previous_count:
        period_movements = period_movements.filter(created_at__gt=previous_count.counted_at)
    movement_totals = period_movements.aggregate(
        incoming=Sum("amount", filter=Q(direction=CashSafeMovement.Direction.IN)),
        outgoing=Sum("amount", filter=Q(direction=CashSafeMovement.Direction.OUT)),
    )
    return render(request, "treasury/cash_safe_count_detail.html", {
        "count": count, "denomination_rows": denomination_rows,
        "previous_count": previous_count, "period_movements": period_movements,
        "period_incoming": movement_totals["incoming"] or Decimal("0.00"),
        "period_outgoing": movement_totals["outgoing"] or Decimal("0.00"),
    })


@login_required
def cash_safe_deposit_list(request):
    company_id, store_id, response = _treasury_context(
        request, "manage.treasury.cash_safe"
    )
    if response:
        return response
    can_confirm = user_has_company_permission(
        request.user, company_id, "authorize.treasury.cash_safe", store_id
    )
    form = CashSafeDepositConfirmationForm(request.POST or None)
    if request.method == "POST":
        if not can_confirm:
            raise PermissionDenied("No tiene permiso para confirmar depósitos bancarios.")
        if form.is_valid():
            try:
                confirm_cash_safe_deposit(
                    company_id=company_id, store_id=store_id, user=request.user,
                    **form.cleaned_data,
                )
            except (TreasuryDomainError, CashSafeDeposit.DoesNotExist, ValidationError) as exc:
                form.add_error(None, str(exc) or "No se encontró el depósito solicitado.")
            else:
                messages.success(
                    request, "Depósito confirmado y movimiento bancario generado."
                )
                return redirect("treasury:cash_safe_deposit_list")
    deposits = CashSafeDeposit.objects.filter(
        cash_movement__company_id=company_id,
        cash_movement__store_id=store_id,
    ).select_related(
        "cash_movement__created_by", "cash_movement__authorized_by",
        "account__bank", "handed_over_by", "deposited_by",
    )
    selected_status = request.GET.get("status", "")
    if selected_status in dict(CashSafeDeposit.Status.choices):
        deposits = deposits.filter(status=selected_status)
    else:
        selected_status = ""
    summary = deposits.aggregate(
        in_transit=Count("id", filter=Q(status=CashSafeDeposit.Status.IN_TRANSIT)),
        deposited=Count("id", filter=Q(status=CashSafeDeposit.Status.DEPOSITED)),
    )
    page_obj = Paginator(deposits, 30).get_page(request.GET.get("page"))
    return render(request, "treasury/cash_safe_deposit_list.html", {
        "form": form, "deposits": page_obj.object_list, "page_obj": page_obj,
        "can_confirm": can_confirm, "selected_status": selected_status,
        "status_choices": CashSafeDeposit.Status.choices,
        "in_transit_count": summary["in_transit"],
        "deposited_count": summary["deposited"],
    })


@login_required
def treasury_dashboard(request, direction=None):
    company_id, store_id, response = _treasury_context(request, "read.treasury")
    if response:
        return response
    can_manage_movements = user_has_company_permission(
        request.user, company_id, "manage.treasury.bank_movements", store_id
    )
    if direction not in {None, BankMovement.Direction.IN, BankMovement.Direction.OUT}:
        direction = None
    form_kind = request.POST.get("form_kind", "")
    if request.method == "POST" and form_kind in {"movement", "reverse"} and not can_manage_movements:
        raise PermissionDenied("No tiene permiso para registrar movimientos bancarios.")
    if request.method == "POST" and form_kind == "reverse":
        try:
            reverse_bank_movement(
                movement_id=request.POST.get("movement_id"),
                company_id=company_id,
                reason=request.POST.get("reason", "").strip(),
                user=request.user,
            )
        except (TreasuryDomainError, BankMovement.DoesNotExist, ValidationError) as exc:
            messages.error(request, str(exc) or "No se encontró el movimiento bancario.")
        else:
            messages.success(request, "Movimiento bancario revertido con trazabilidad.")
        target = {
            BankMovement.Direction.IN: "treasury:bank_income_list",
            BankMovement.Direction.OUT: "treasury:bank_expense_list",
        }.get(direction, "treasury:dashboard")
        return redirect(target)
    form_data = request.POST.copy() if form_kind == "movement" else None
    if form_data is not None and direction:
        form_data["direction"] = direction
    movement_form = BankMovementForm(
        form_data, company_id=company_id, fixed_direction=direction
    )
    if request.method == "POST" and form_kind == "movement" and movement_form.is_valid():
        try:
            register_bank_movement(
                company_id=company_id, user=request.user, **movement_form.cleaned_data
            )
        except TreasuryDomainError as exc:
            movement_form.add_error("amount", str(exc))
        else:
            messages.success(request, "Movimiento bancario del sistema registrado.")
            target = {
                BankMovement.Direction.IN: "treasury:bank_income_list",
                BankMovement.Direction.OUT: "treasury:bank_expense_list",
            }.get(direction, "treasury:dashboard")
            return redirect(target)
    accounts = list(
        BankAccount.objects.filter(company_id=company_id).select_related("bank")
    )
    for account in accounts:
        account.current_balance = bank_account_balance(account)
    movements = BankMovement.objects.filter(company_id=company_id).select_related(
        "account__bank", "destination_account__bank", "transfer_source__account__bank",
        "created_by", "safe_movement", "reversed_movement"
    )
    if direction:
        movements = movements.filter(direction=direction)
    selected_account = request.GET.get("account", "")
    date_from = parse_date(request.GET.get("date_from", ""))
    date_to = parse_date(request.GET.get("date_to", ""))
    search = request.GET.get("q", "").strip()
    try:
        UUID(selected_account)
    except (TypeError, ValueError, AttributeError):
        selected_account = ""
    if selected_account:
        movements = movements.filter(account_id=selected_account)
    if date_from:
        movements = movements.filter(operation_date__gte=date_from)
    if date_to:
        movements = movements.filter(operation_date__lte=date_to)
    if search:
        movements = movements.filter(
            Q(movement_number__icontains=search)
            | Q(reference__icontains=search)
            | Q(description__icontains=search)
        )
    page_obj = Paginator(movements, 50).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "treasury/dashboard.html", {
        "accounts": accounts,
        "page_obj": page_obj,
        "movement_form": movement_form,
        "form_kind": form_kind,
        "can_manage_movements": can_manage_movements,
        "fixed_direction": direction,
        "selected_account": selected_account,
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "search": search,
        "pagination_query": query.urlencode(),
    })


@login_required
def bank_movement_export_xlsx(request):
    company_id, store_id, response = _treasury_context(request, "read.treasury")
    if response:
        return response
    date_from = parse_date(request.GET.get("date_from", ""))
    date_to = parse_date(request.GET.get("date_to", ""))
    if date_from and date_to and date_to < date_from:
        return HttpResponse("El rango de fechas no es válido.", status=400)
    movements = BankMovement.objects.filter(company_id=company_id).select_related(
        "account__bank", "destination_account__bank", "created_by"
    ).order_by("operation_date", "created_at", "id")
    direction = request.GET.get("direction", "")
    if direction in dict(BankMovement.Direction.choices):
        movements = movements.filter(direction=direction)
    account_id = request.GET.get("account", "")
    try:
        UUID(account_id)
    except (TypeError, ValueError, AttributeError):
        account_id = ""
    if account_id:
        movements = movements.filter(account_id=account_id)
    if date_from:
        movements = movements.filter(operation_date__gte=date_from)
    if date_to:
        movements = movements.filter(operation_date__lte=date_to)
    search = request.GET.get("q", "").strip()
    if search:
        movements = movements.filter(
            Q(movement_number__icontains=search)
            | Q(reference__icontains=search)
            | Q(description__icontains=search)
        )
    from .reports import build_bank_movement_report

    content = build_bank_movement_report(
        movements,
        company_name=Company.objects.get(pk=company_id).name,
        date_from=date_from,
        date_to=date_to,
    )
    filename = "reporte_movimientos_bancarios"
    if date_from or date_to:
        filename += f"_{date_from or 'inicio'}_{date_to or 'actual'}"
    export = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    export["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
    return export


@login_required
def bank_account_create(request):
    company_id, response = _bank_account_settings_context(request)
    if response:
        return response
    form = BankAccountForm(request.POST or None, company_id=company_id)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Cuenta bancaria registrada correctamente.")
        return redirect(f"{reverse('users:configuracion')}?item=cuentas_bancarias")
    return render(request, "treasury/bank_account_form.html", {
        "form": form, "active_tab": "configuracion", "is_edit": False,
    })


@login_required
def bank_account_update(request, pk):
    company_id, response = _bank_account_settings_context(request)
    if response:
        return response
    account = get_object_or_404(BankAccount, pk=pk, company_id=company_id)
    form = BankAccountForm(
        request.POST or None, instance=account, company_id=company_id
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Cuenta bancaria actualizada correctamente.")
        return redirect(f"{reverse('users:configuracion')}?item=cuentas_bancarias")
    return render(request, "treasury/bank_account_form.html", {
        "form": form, "account": account, "active_tab": "configuracion", "is_edit": True,
    })


@login_required
def bank_account_toggle(request, pk):
    company_id, response = _bank_account_settings_context(request)
    if response:
        return response
    if request.method != "POST":
        raise PermissionDenied("Esta acción requiere una solicitud POST.")
    account = get_object_or_404(BankAccount, pk=pk, company_id=company_id)
    if account.active and account.means_of_payments.filter(active=True).exists():
        messages.error(
            request,
            "No puede desactivar una cuenta vinculada a medios de pago activos.",
        )
        return redirect(f"{reverse('users:configuracion')}?item=cuentas_bancarias")
    if account.active and account.cash_safe_deposits.filter(
        status__in=(CashSafeDeposit.Status.REQUESTED, CashSafeDeposit.Status.IN_TRANSIT)
    ).exists():
        messages.error(
            request,
            "No puede desactivar una cuenta con depósitos de caja fuerte pendientes.",
        )
        return redirect(f"{reverse('users:configuracion')}?item=cuentas_bancarias")
    account.active = not account.active
    account.save(update_fields=("active", "updated_at"))
    messages.success(
        request, f"Cuenta bancaria {'activada' if account.active else 'desactivada'} correctamente."
    )
    return redirect(f"{reverse('users:configuracion')}?item=cuentas_bancarias")


@login_required
def bank_reconciliation_list(request):
    company_id, store_id, response = _treasury_context(
        request, "reconcile.treasury.bank"
    )
    if response:
        return response
    form = BankStatementImportForm(
        request.POST or None, request.FILES or None, company_id=company_id
    )
    if request.method == "POST" and form.is_valid():
        data = {key: value for key, value in form.cleaned_data.items() if key != "statement_file"}
        try:
            statement = import_bank_statement(
                company_id=company_id,
                user=request.user,
                uploaded_file=form.cleaned_data["statement_file"],
                **data,
            )
        except (TreasuryDomainError, ValidationError) as exc:
            form.add_error("statement_file", str(exc))
        else:
            messages.success(request, "Extracto importado. Ya puede conciliar sus movimientos.")
            return redirect("treasury:bank_reconciliation_detail", pk=statement.pk)
    statements = BankStatement.objects.filter(company_id=company_id).select_related(
        "account__bank", "created_by", "reconciled_by"
    )
    selected_account = request.GET.get("account", "")
    selected_status = request.GET.get("status", "")
    date_from = parse_date(request.GET.get("date_from", ""))
    date_to = parse_date(request.GET.get("date_to", ""))
    try:
        UUID(selected_account)
    except (ValueError, TypeError, AttributeError):
        selected_account = ""
    if selected_account:
        statements = statements.filter(account_id=selected_account)
    if selected_status in dict(BankStatement.Status.choices):
        statements = statements.filter(status=selected_status)
    else:
        selected_status = ""
    if date_from:
        statements = statements.filter(date_to__gte=date_from)
    if date_to:
        statements = statements.filter(date_from__lte=date_to)
    statements = statements.annotate(
        line_count=Count("lines", distinct=True),
        matched_count=Count(
            "lines", filter=Q(lines__reconciliation_matches__isnull=False), distinct=True
        ),
    )
    return render(request, "treasury/bank_reconciliation_list.html", {
        "form": form,
        "statements": statements,
        "accounts": BankAccount.objects.filter(company_id=company_id).select_related("bank"),
        "status_choices": BankStatement.Status.choices,
        "selected_account": selected_account,
        "selected_status": selected_status,
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
    })


@login_required
def bank_reconciliation_detail(request, pk):
    company_id, store_id, response = _treasury_context(
        request, "reconcile.treasury.bank"
    )
    if response:
        return response
    statement = get_object_or_404(
        BankStatement.objects.select_related("account__bank", "reconciled_by"),
        pk=pk, company_id=company_id,
    )
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "match":
                match_bank_statement_line(
                    line_id=request.POST.get("line_id"),
                    movement_id=request.POST.get("movement_id"),
                    company_id=company_id,
                    user=request.user,
                )
                messages.success(request, "Movimiento conciliado.")
            elif action == "unmatch":
                unmatch_bank_statement_line(
                    line_id=request.POST.get("line_id"), company_id=company_id,
                    movement_id=request.POST.get("movement_id"),
                )
                messages.success(request, "Coincidencia retirada.")
            elif action == "close":
                close_bank_statement(
                    statement_id=statement.pk, company_id=company_id, user=request.user
                )
                messages.success(request, "Conciliación bancaria cerrada correctamente.")
            else:
                raise TreasuryDomainError("Acción de conciliación inválida.")
        except (
            TreasuryDomainError,
            ObjectDoesNotExist,
        ) as exc:
            messages.error(request, str(exc) or "No se encontró el movimiento solicitado.")
        return redirect("treasury:bank_reconciliation_detail", pk=statement.pk)

    lines = list(
        statement.lines.prefetch_related(
            "reconciliation_matches__bank_movement",
            "reconciliation_matches__matched_by",
        )
    )
    matched_movement_ids = [
        match.bank_movement_id
        for line in lines for match in line.reconciliation_matches.all()
    ]
    available = BankMovement.objects.filter(
        company_id=company_id,
        account=statement.account,
        status=BankMovement.Status.POSTED,
        operation_date__range=(statement.date_from, statement.date_to),
    ).exclude(pk__in=matched_movement_ids).order_by("operation_date", "created_at")
    for line in lines:
        line.matches = list(line.reconciliation_matches.all())
        line.matched_total = sum(
            (match.bank_movement.amount for match in line.matches), Decimal("0.00")
        )
        line.remaining_amount = line.amount - line.matched_total
        line.candidates = sorted(
            [
                movement for movement in available
                if movement.direction == line.direction
                and movement.amount <= line.remaining_amount
            ],
            key=lambda movement: (
                not bool(line.reference and movement.reference == line.reference),
                abs((movement.operation_date - line.transaction_date).days),
                movement.operation_date,
            ),
        )

    totals = statement.lines.aggregate(
        incoming=Sum("amount", filter=Q(direction=BankMovement.Direction.IN)),
        outgoing=Sum("amount", filter=Q(direction=BankMovement.Direction.OUT)),
    )
    imported_closing = statement.opening_balance + (totals["incoming"] or Decimal("0.00")) - (
        totals["outgoing"] or Decimal("0.00")
    )
    system_closing = bank_account_balance_at(statement.account, statement.date_to)
    return render(request, "treasury/bank_reconciliation_detail.html", {
        "statement": statement,
        "lines": lines,
        "incoming": totals["incoming"] or Decimal("0.00"),
        "outgoing": totals["outgoing"] or Decimal("0.00"),
        "imported_closing": imported_closing,
        "system_closing": system_closing,
        "balance_difference": statement.closing_balance - system_closing,
    })
