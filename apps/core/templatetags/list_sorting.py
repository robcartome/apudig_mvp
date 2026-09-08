from django import template


register = template.Library()


@register.inclusion_tag("components/sortable_header.html", takes_context=True)
def sortable_header(context, field, label, css_class=""):
    """Render a sortable table heading while retaining active GET filters."""
    state = context.get("table_sort", {})
    is_active = state.get("key") == field
    current_direction = state.get("direction", "asc")
    next_direction = "desc" if is_active and current_direction == "asc" else "asc"

    params = context["request"].GET.copy()
    params.pop("page", None)
    params["sort"] = field
    params["dir"] = next_direction

    return {
        "label": label,
        "css_class": css_class,
        "query_string": params.urlencode(),
        "is_active": is_active,
        "direction": current_direction,
        "aria_sort": (
            "ascending" if is_active and current_direction == "asc"
            else "descending" if is_active
            else "none"
        ),
    }
