from django.db.models import Case, IntegerField, Value, When

from .models import NotificationPriority, NotificationRecipient


def notification_recipients_for_user(
    *, user, company_id, store_id, status=None, notification_type=None, priority=None,
):
    queryset = NotificationRecipient.objects.filter(
        user=user,
        notification__company_id=company_id,
        notification__store_id=store_id,
        notification__is_active=True,
    ).select_related("notification")
    if status == "unread":
        queryset = queryset.filter(read_at__isnull=True)
    elif status == "read":
        queryset = queryset.filter(read_at__isnull=False)
    if notification_type:
        queryset = queryset.filter(notification__notification_type=notification_type)
    if priority:
        queryset = queryset.filter(notification__priority=priority)
    return queryset.annotate(
        priority_order=Case(
            When(notification__priority=NotificationPriority.HIGH, then=Value(0)),
            When(notification__priority=NotificationPriority.WARNING, then=Value(1)),
            default=Value(2), output_field=IntegerField(),
        )
    ).order_by("priority_order", "notification__due_date", "-notification__updated_at")


def unread_notification_count(*, user, company_id, store_id):
    return notification_recipients_for_user(
        user=user, company_id=company_id, store_id=store_id, status="unread"
    ).count()

