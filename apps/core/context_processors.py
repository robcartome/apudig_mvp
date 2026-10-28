from apps.users.permissions import user_has_company_permission


def global_notifications_context(request):
    """Build small, actionable navbar notifications for the active scope."""
    context = {"notification_center": None}
    if not request.user.is_authenticated:
        return context

    company_id = getattr(request, "active_company_id", None)
    store_id = getattr(request, "active_store_id", None)
    if not company_id or not store_id:
        return context
    if not user_has_company_permission(
        request.user, company_id, "read.purchases.documents", store_id
    ):
        return context

    context["notification_center"] = True
    return context
