"""Compose the home dashboard from scoped domain selectors."""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.core.currency import currency_choices
from apps.inventory.selectors import get_dashboard_stock
from apps.purchases.selectors import get_dashboard_purchases
from apps.sales.selectors import get_dashboard_sales
from apps.users.permissions import user_has_company_permission


PERIODS = (("today", "Hoy"), ("7d", "Últimos 7 días"), ("month", "Este mes"), ("30d", "Últimos 30 días"))


def get_dashboard_context(request):
    today = timezone.localdate()
    period = request.GET.get("period", "month")
    if period not in dict(PERIODS):
        period = "month"
    currency = request.GET.get("currency", "PEN")
    if currency not in dict(currency_choices()):
        currency = "PEN"
    date_from = {
        "today": today, "7d": today - timedelta(days=6),
        "month": today.replace(day=1), "30d": today - timedelta(days=29),
    }[period]
    company_id, store_id = request.active_company_id, request.active_store_id
    permissions = {
        name: bool(store_id) and user_has_company_permission(request.user, company_id, code, store_id)
        for name, code in {
            "sales": "read.sales.documents", "create_sale": "manage.sales.documents",
            "purchases": "read.purchases.documents", "create_purchase": "manage.purchases.documents",
            "inventory": "read.inventory.products", "create_product": "manage.inventory.products",
            "pos": "read.pos", "treasury": "read.treasury",
        }.items()
    }
    context = {
        "period": period, "periods": PERIODS, "period_label": dict(PERIODS)[period],
        "currency": currency, "currencies": currency_choices(), "date_from": date_from,
        "date_to": today, "updated_at": timezone.localtime(), "dashboard_permissions": permissions,
    }
    if not store_id:
        return context
    days = (today - date_from).days + 1
    start = timezone.make_aware(datetime.combine(date_from, time.min))
    end = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min))
    if permissions["sales"]:
        sales = get_dashboard_sales(company_id, store_id, start, end, start - timedelta(days=days), currency)
        previous = sales["previous"]
        change = (sales["total"] - previous) / abs(previous) * 100 if previous else None
        sales["change"] = abs(change) if change is not None else None
        sales["change_direction"] = "up" if change is not None and change >= 0 else "down"
        sales["average"] = sales["total"] / sales["count"] if sales["count"] else Decimal("0")
        context["sales"] = sales
        daily = {row["day"]: row["total"] for row in sales["daily"]}
        series = [
            {
                "day": date_from + timedelta(days=i),
                "total": daily.get(date_from + timedelta(days=i), Decimal("0")),
            }
            for i in range(days)
        ]
        high = max(max(row["total"] for row in series), Decimal("1"))
        low = min(min(row["total"] for row in series), Decimal("0"))
        for i, row in enumerate(series):
            row["x"] = round(20 + i * 720 / max(days - 1, 1), 2) if days > 1 else 380
            row["y"] = round(float(170 - (row["total"] - low) / (high - low) * 140), 2)
        context["chart"] = {
            "series": series, "points": " ".join(f'{row["x"]},{row["y"]}' for row in series),
            "high": high, "low": low, "zero_y": round(float(170 - (0 - low) / (high - low) * 140), 2),
            "has_activity": sales["count"] > 0,
        }
    if permissions["purchases"]:
        context["purchases"] = get_dashboard_purchases(company_id, store_id, date_from, today, currency)
    if permissions["inventory"]:
        context["stock"] = get_dashboard_stock(company_id, store_id)
    return context
