from django import template
from django.core.exceptions import PermissionDenied
from apps.websites.permissions import website_capabilities

register = template.Library()


@register.simple_tag
def website_access(request):
    if not hasattr(request, "_website_menu_capabilities"):
        try:
            _, capabilities = website_capabilities(request.user, getattr(request, "active_company_id", None), getattr(request, "active_store_id", None))
        except PermissionDenied:
            capabilities = {}
        request._website_menu_capabilities = capabilities
    return request._website_menu_capabilities
