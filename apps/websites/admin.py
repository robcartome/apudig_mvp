"""Platform inspection only. Editorial/domain writes use authorized services."""
from django.apps import apps
from django.contrib import admin


class WebsiteInspectionAdmin(admin.ModelAdmin):
    actions = None
    change_list_template = "admin/websites/change_list.html"

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


for model in apps.get_app_config("websites").get_models():
    admin.site.register(model, WebsiteInspectionAdmin)
