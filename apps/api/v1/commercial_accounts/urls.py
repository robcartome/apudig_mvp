from django.urls import path
from .views import CommercialSessionAPIView, CommercialProfileAPIView, AdministrativeAccountsAPIView, AdministrativeAccountAPIView
from .registration import RegistrationPolicyAPIView, RegistrationStartAPIView, RegistrationCompleteAPIView, AdministrativeRegistrationPolicyAPIView, AdministrativeRegistrationsAPIView, AdministrativeRegistrationReviewAPIView, RegistrationCustomerOptionsAPIView
from .quotation import CommercialCartQuoteAPIView, CommercialCartConfirmAPIView
from .orders import OrderRequestsAPIView, OrderRequestDetailAPIView, CancelOrderRequestAPIView, AccountPrivacyAPIView

urlpatterns = [
    path("storefront/sites/<str:hostname>/account/privacy/", AccountPrivacyAPIView.as_view()),
    path("storefront/sites/<str:hostname>/account/order-requests/", OrderRequestsAPIView.as_view()),
    path("storefront/sites/<str:hostname>/account/order-requests/<uuid:request_id>/", OrderRequestDetailAPIView.as_view()),
    path("storefront/sites/<str:hostname>/account/order-requests/<uuid:request_id>/cancel/", CancelOrderRequestAPIView.as_view()),
    path("storefront/sites/<str:hostname>/account/cart/quote/", CommercialCartQuoteAPIView.as_view()),
    path("storefront/sites/<str:hostname>/account/cart/confirm/", CommercialCartConfirmAPIView.as_view()),
    path("storefront/sites/<str:hostname>/registration-policy/", RegistrationPolicyAPIView.as_view()),
    path("storefront/sites/<str:hostname>/registrations/", RegistrationStartAPIView.as_view()),
    path("storefront/sites/<str:hostname>/registrations/complete/", RegistrationCompleteAPIView.as_view()),
    path("websites/<uuid:website_id>/registration-policy/", AdministrativeRegistrationPolicyAPIView.as_view()),
    path("websites/<uuid:website_id>/registrations/", AdministrativeRegistrationsAPIView.as_view()),
    path("websites/<uuid:website_id>/registrations/<uuid:registration_id>/review/", AdministrativeRegistrationReviewAPIView.as_view()),
    path("websites/<uuid:website_id>/registration-customer-options/", RegistrationCustomerOptionsAPIView.as_view()),
    path("storefront/sites/<str:hostname>/account/session/", CommercialSessionAPIView.as_view(), name="api_v1_commercial_session"),
    path("storefront/sites/<str:hostname>/account/", CommercialProfileAPIView.as_view(), name="api_v1_commercial_profile"),
    path("websites/<uuid:website_id>/commercial-accounts/", AdministrativeAccountsAPIView.as_view(), name="api_v1_commercial_accounts"),
    path("websites/<uuid:website_id>/commercial-accounts/<uuid:account_id>/", AdministrativeAccountAPIView.as_view(), name="api_v1_commercial_account"),
]
