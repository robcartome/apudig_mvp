from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.companies.models import UserCompanyAccess
from apps.users.models import UserRole, UserStore
from apps.users.permissions import user_has_company_permission

from .models import Notification, NotificationRecipient


def eligible_notification_users(company_id, store_id, permission_code):
    """Resolve active users that can read the source module in this scope."""
    user_ids = set(
        UserCompanyAccess.objects.filter(
            company_id=company_id,
        ).filter(Q(store_id=store_id) | Q(store__isnull=True)).values_list("user_id", flat=True)
    )
    user_ids.update(
        UserStore.objects.filter(
            store_id=store_id, is_active=True, user__is_active=True,
        ).values_list("user_id", flat=True)
    )
    user_ids.update(
        UserRole.objects.filter(
            company_id=company_id, user__is_active=True,
        ).values_list("user_id", flat=True)
    )
    users = get_user_model().objects.filter(
        Q(pk__in=user_ids) | Q(is_superuser=True), is_active=True,
    ).distinct()
    return [
        user for user in users
        if user_has_company_permission(user, company_id, permission_code, store_id)
    ]


@transaction.atomic
def upsert_notification(*, recipients, reset_read=False, **values):
    lookup = {
        "company_id": values.pop("company_id"),
        "store_id": values.pop("store_id"),
        "deduplication_key": values.pop("deduplication_key"),
    }
    notification, created = Notification.objects.select_for_update().get_or_create(
        **lookup, defaults=values,
    )
    if not created:
        was_inactive = not notification.is_active
        changed_to_high = (
            notification.priority != values.get("priority")
            and values.get("priority") == "HIGH"
        )
        for field, value in values.items():
            setattr(notification, field, value)
        notification.save()
        reset_read = reset_read or changed_to_high or was_inactive
    recipient_rows = []
    for user in recipients:
        recipient, _ = NotificationRecipient.objects.get_or_create(
            notification=notification, user=user
        )
        recipient_rows.append(recipient)
    if reset_read and recipient_rows:
        NotificationRecipient.objects.filter(
            pk__in=[row.pk for row in recipient_rows]
        ).update(read_at=None)
    return notification


@transaction.atomic
def resolve_notifications(
    *, company_id, store_id, notification_type, active_keys,
    source_ids=None, source_document_id=None,
):
    queryset = Notification.objects.select_for_update().filter(
        company_id=company_id,
        store_id=store_id,
        notification_type=notification_type,
        is_active=True,
    )
    if source_ids is not None:
        queryset = queryset.filter(source_id__in=[str(value) for value in source_ids])
    if source_document_id is not None:
        queryset = queryset.filter(
            metadata__purchase_document_id=str(source_document_id)
        )
    queryset.exclude(deduplication_key__in=active_keys).update(
        is_active=False, resolved_at=timezone.now()
    )


def mark_notification_read(recipient, *, read_at=None):
    if recipient.read_at is None:
        recipient.read_at = read_at or timezone.now()
        recipient.save(update_fields=("read_at",))
    return recipient


def mark_all_notifications_read(*, user, company_id, store_id):
    return NotificationRecipient.objects.filter(
        user=user,
        read_at__isnull=True,
        notification__company_id=company_id,
        notification__store_id=store_id,
        notification__is_active=True,
    ).update(read_at=timezone.now())

