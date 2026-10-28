from datetime import timedelta
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, OuterRef, Subquery, Sum, Value
from django.db import transaction
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import CompanyOperationalSettings, Store
from apps.notifications.models import NotificationPriority, NotificationType
from apps.notifications.services import (
    eligible_notification_users, resolve_notifications, upsert_notification,
)

from .models import (
    PurchaseDocumentStatus, PurchasePayableInstallment, SupplierPaymentAllocation,
    SupplierPaymentStatus,
)


def _outstanding_installments(*, company_id, store_id, document_id=None):
    money_field = DecimalField(max_digits=14, decimal_places=2)
    paid_subquery = (
        SupplierPaymentAllocation.objects.filter(
            installment_id=OuterRef("pk"),
            payment__status=SupplierPaymentStatus.REGISTERED,
        )
        .values("installment_id")
        .annotate(total=Sum("amount"))
        .values("total")[:1]
    )
    queryset = PurchasePayableInstallment.objects.filter(
        purchase_document__company_id=company_id,
        purchase_document__store_id=store_id,
        purchase_document__document_status=PurchaseDocumentStatus.REGISTERED,
        purchase_document__payment_method__is_cash=False,
    )
    if document_id is not None:
        queryset = queryset.filter(purchase_document_id=document_id)
    return (
        queryset.annotate(
            paid_amount=Coalesce(
                Subquery(paid_subquery, output_field=money_field),
                Value(Decimal("0")), output_field=money_field,
            )
        )
        .annotate(
            balance=ExpressionWrapper(
                F("amount") - F("paid_amount"), output_field=money_field
            )
        )
        .filter(balance__gt=0)
        .select_related("purchase_document", "purchase_document__supplier")
    )


def sync_purchase_payable_notifications(
    *, company_id=None, store_id=None, document_id=None, today=None,
):
    """Synchronize purchase installment due events without duplicating them."""
    today = today or timezone.localdate()
    stores = Store.objects.filter(active=True)
    if company_id is not None:
        stores = stores.filter(company_id=company_id)
    if store_id is not None:
        stores = stores.filter(pk=store_id)

    synchronized = 0
    for store in stores.select_related("company"):
        settings, _ = CompanyOperationalSettings.objects.get_or_create(
            company_id=store.company_id
        )
        threshold = settings.purchase_due_notification_days
        cutoff = today + timedelta(days=threshold)
        installments = _outstanding_installments(
            company_id=store.company_id, store_id=store.pk, document_id=document_id
        ).filter(due_date__lte=cutoff).order_by("due_date", "sequence")
        recipients = eligible_notification_users(
            store.company_id, store.pk, "read.purchases.documents"
        )
        active_keys = []
        for installment in installments:
            document = installment.purchase_document
            overdue_days = max((today - installment.due_date).days, 0)
            is_overdue = installment.due_date < today
            state = "OVERDUE" if is_overdue else "DUE_SOON"
            key = f"purchase_installment_due:{installment.pk}"
            active_keys.append(key)
            reference = "-".join(
                part for part in (document.series, document.number) if part
            ) or str(document.pk)
            if is_overdue:
                title = f"Compra {reference} vencida"
                message = (
                    f"{document.supplier_name} · {overdue_days} día(s) de atraso"
                )
                priority = NotificationPriority.HIGH
            else:
                remaining_days = (installment.due_date - today).days
                title = f"Compra {reference} próxima a vencer"
                message = (
                    f"{document.supplier_name} · vence "
                    f'{"hoy" if remaining_days == 0 else f"en {remaining_days} día(s)"}'
                )
                priority = NotificationPriority.WARNING
            upsert_notification(
                company_id=store.company_id,
                store_id=store.pk,
                recipients=recipients,
                deduplication_key=key,
                notification_type=NotificationType.PURCHASE_DUE,
                priority=priority,
                title=title,
                message=message,
                source_type="purchases.PurchasePayableInstallment",
                source_id=str(installment.pk),
                target_url=reverse("purchases:document_detail", args=[document.pk]),
                due_date=installment.due_date,
                amount=installment.balance,
                currency=document.currency,
                metadata={
                    "state": state,
                    "purchase_document_id": str(document.pk),
                    "supplier_id": str(document.supplier_id),
                    "supplier_name": document.supplier_name,
                    "sequence": installment.sequence,
                    "overdue_days": overdue_days,
                },
                is_active=True,
                resolved_at=None,
            )
            synchronized += 1
        resolve_notifications(
            company_id=store.company_id,
            store_id=store.pk,
            notification_type=NotificationType.PURCHASE_DUE,
            active_keys=active_keys,
            source_document_id=document_id,
        )
    return synchronized


def schedule_purchase_payable_notification_sync(document):
    company_id = document.company_id
    store_id = document.store_id
    document_id = document.pk
    transaction.on_commit(lambda: sync_purchase_payable_notifications(
        company_id=company_id, store_id=store_id, document_id=document_id
    ))

