from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.utils.dateparse import parse_date


def read_list_filters(request, *, default_current_month=True):
    """Parse common list filters while preserving their original form values."""
    today = timezone.localdate()
    month_start = today.replace(day=1)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    defaults = (
        (month_start.isoformat(), (next_month - timedelta(days=1)).isoformat())
        if default_current_month
        else ("", "")
    )

    values = {
        "q": request.GET.get("q", "").strip(),
        "date_from": request.GET.get("date_from", defaults[0]),
        "date_to": request.GET.get("date_to", defaults[1]),
        "created_from": request.GET.get("created_from", ""),
        "created_to": request.GET.get("created_to", ""),
        "series": request.GET.get("series", "").strip(),
        "number": request.GET.get("number", "").strip(),
        "party": (
            request.GET.get("party")
            or request.GET.get("customer")
            or request.GET.get("supplier")
            or ""
        ).strip(),
        "total_min": request.GET.get("total_min", "").strip(),
        "total_max": request.GET.get("total_max", "").strip(),
        "status": request.GET.get("status", ""),
    }
    values["date_from_value"] = _date_or_none(values["date_from"])
    values["date_to_value"] = _date_or_none(values["date_to"])
    values["created_from_value"] = _date_or_none(values["created_from"])
    values["created_to_value"] = _date_or_none(values["created_to"])
    values["total_min_value"] = _decimal_or_none(values["total_min"])
    values["total_max_value"] = _decimal_or_none(values["total_max"])
    values["advanced_filters_active"] = any(
        values[key]
        for key in (
            "created_from", "created_to", "series", "number", "party",
            "total_min", "total_max", "status",
        )
    )
    query_params = request.GET.copy()
    query_params.pop("page", None)
    values["pagination_query"] = query_params.urlencode()
    return values


def _date_or_none(value):
    try:
        return parse_date(value) if value else None
    except ValueError:
        return None


def _decimal_or_none(value):
    try:
        parsed = Decimal(value) if value else None
        return parsed if parsed is None or parsed.is_finite() else None
    except (InvalidOperation, ValueError):
        return None
