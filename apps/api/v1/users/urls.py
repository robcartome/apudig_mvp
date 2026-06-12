from django.urls import path

from apps.api.v1.users.views import (
    AssignRoleAPIView,
    AuthMeAPIView,
    LogoutAPIView,
    MyCompaniesAPIView,
    PermissionsAPIView,
    RegisterUserAPIView,
    RemoveRoleAPIView,
    RolesAPIView,
    SelectCompanyAPIView,
    TokenObtainAPIView,
    TokenRefreshAPIView,
    UsersListAPIView,
)

urlpatterns = [
    path("auth/token/", TokenObtainAPIView.as_view(), name="api_v1_token_obtain"),
    path("auth/refresh/", TokenRefreshAPIView.as_view(), name="api_v1_token_refresh"),
    path("auth/me/", AuthMeAPIView.as_view(), name="api_v1_auth_me"),
    path("auth/my-companies/", MyCompaniesAPIView.as_view(), name="api_v1_auth_my_companies"),
    path("auth/select-company/", SelectCompanyAPIView.as_view(), name="api_v1_auth_select_company"),
    path("auth/logout/", LogoutAPIView.as_view(), name="api_v1_auth_logout"),
    path("auth/users/", UsersListAPIView.as_view(), name="api_v1_auth_users"),
    path("auth/register/", RegisterUserAPIView.as_view(), name="api_v1_auth_register"),
    path("auth/roles/", RolesAPIView.as_view(), name="api_v1_auth_roles"),
    path("auth/roles/assign/", AssignRoleAPIView.as_view(), name="api_v1_auth_roles_assign"),
    path("auth/roles/remove/", RemoveRoleAPIView.as_view(), name="api_v1_auth_roles_remove"),
    path("auth/permissions/", PermissionsAPIView.as_view(), name="api_v1_auth_permissions"),
]
