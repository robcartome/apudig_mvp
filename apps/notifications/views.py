from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST

from apps.users.permissions import user_has_company_permission

from .models import NotificationPriority, NotificationRecipient, NotificationType
from .selectors import notification_recipients_for_user, unread_notification_count
from .services import mark_all_notifications_read, mark_notification_read


def _scope(request):
    company_id = getattr(request, "active_company_id", None)
    store_id = getattr(request, "active_store_id", None)
    if not company_id or not store_id:
        raise Http404("Selecciona una empresa y sucursal.")
    if not user_has_company_permission(
        request.user, company_id, "read.purchases.documents", store_id
    ):
        return company_id, store_id, False
    return company_id, store_id, True


@login_required
def notification_list(request):
    company_id, store_id, allowed = _scope(request)
    if not allowed:
        return HttpResponseForbidden("No tienes permiso para ver notificaciones.")
    status = request.GET.get("status", "")
    notification_type = request.GET.get("type", "")
    priority = request.GET.get("priority", "")
    sort = request.GET.get("sort", "priority")
    queryset = notification_recipients_for_user(
        user=request.user,
        company_id=company_id,
        store_id=store_id,
        status=status,
        notification_type=notification_type,
        priority=priority,
    )
    if sort == "newest":
        queryset = queryset.order_by("-notification__updated_at")
    elif sort == "oldest":
        queryset = queryset.order_by("notification__updated_at")
    elif sort == "due_date":
        queryset = queryset.order_by("notification__due_date", "-notification__updated_at")
    page_obj = Paginator(queryset, 25).get_page(request.GET.get("page"))
    return render(request, "notifications/list.html", {
        "page_obj": page_obj,
        "status": status,
        "notification_type": notification_type,
        "priority": priority,
        "sort": sort,
        "notification_types": NotificationType.choices,
        "priorities": NotificationPriority.choices,
    })


@login_required
@require_GET
def notification_dropdown(request):
    company_id, store_id, allowed = _scope(request)
    if not allowed:
        return JsonResponse({"error": "No autorizado."}, status=403)
    status = request.GET.get("status", "unread")
    if status not in ("all", "unread"):
        status = "unread"
    queryset = notification_recipients_for_user(
        user=request.user,
        company_id=company_id,
        store_id=store_id,
        status="unread" if status == "unread" else None,
    )
    recipients = list(queryset[:8])
    html = render_to_string(
        "notifications/partials/dropdown_items.html",
        {"notification_recipients": recipients},
        request=request,
    )
    return JsonResponse({
        "html": html,
        "unread_count": unread_notification_count(
            user=request.user, company_id=company_id, store_id=store_id
        ),
        "total": queryset.count(),
        "status": status,
    })


@login_required
@require_GET
def notification_unread_count(request):
    company_id, store_id, allowed = _scope(request)
    if not allowed:
        return JsonResponse({"error": "No autorizado."}, status=403)
    return JsonResponse({
        "unread_count": unread_notification_count(
            user=request.user, company_id=company_id, store_id=store_id
        )
    })


@login_required
@require_POST
def notification_mark_read(request, pk):
    company_id, store_id, allowed = _scope(request)
    if not allowed:
        return JsonResponse({"error": "No autorizado."}, status=403)
    try:
        recipient = NotificationRecipient.objects.select_related("notification").get(
            notification_id=pk,
            user=request.user,
            notification__company_id=company_id,
            notification__store_id=store_id,
            notification__is_active=True,
        )
    except NotificationRecipient.DoesNotExist:
        raise Http404
    mark_notification_read(recipient)
    return JsonResponse({
        "ok": True,
        "target_url": recipient.notification.target_url,
        "unread_count": unread_notification_count(
            user=request.user, company_id=company_id, store_id=store_id
        ),
    })


@login_required
@require_POST
def notification_mark_all_read(request):
    company_id, store_id, allowed = _scope(request)
    if not allowed:
        return JsonResponse({"error": "No autorizado."}, status=403)
    updated = mark_all_notifications_read(
        user=request.user, company_id=company_id, store_id=store_id
    )
    return JsonResponse({"ok": True, "updated": updated, "unread_count": 0})

