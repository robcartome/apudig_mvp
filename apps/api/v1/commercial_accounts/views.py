import hashlib

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.cache import patch_vary_headers
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter

from apps.api.v1.websites.views import WebsiteAPIView
from apps.api.v1.website_catalog.views import query_values
from apps.api.v1.website_catalog.serializers import SearchPageQuerySerializer
from apps.partners.models import SalesCustomerProfile
from apps.websites.accounts import set_wholesale_approval
from apps.websites.catalog.services import authorized_website
from apps.websites.commercial_sessions import start_session, resolve_session
from apps.websites.errors import WebsiteError
from apps.websites.models import CommercialAccount
from .authentication import CommercialIdentityAuthentication, CommercialJWTAuthentication
from .serializers import WholesaleApprovalSerializer, CommercialTokenSerializer, CommercialProfileSerializer, AdministrativeAccountSerializer, AdministrativeAccountsPageSerializer


def commercial_auth_response(operation, *args):
    try:
        return Response(operation(*args), headers={"Cache-Control": "private, no-store"})
    except WebsiteError as exc:
        return Response({"code": exc.code, "message": str(exc), "fields": exc.fields}, status=exc.status, headers={"Cache-Control": "private, no-store"})
    except ObjectDoesNotExist:
        return Response({"code": "NOT_FOUND", "message": "Website no disponible."}, status=404, headers={"Cache-Control": "private, no-store"})


class CommercialAPIView(WebsiteAPIView):
    authentication_classes = [CommercialJWTAuthentication]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        patch_vary_headers(response, ("Authorization",))
        return response


class CommercialSessionAPIView(CommercialAPIView):
    authentication_classes = [CommercialIdentityAuthentication]

    @extend_schema(tags=["Commercial accounts"], request=None, responses={200: CommercialTokenSerializer})
    def post(self, request, hostname):
        if request.data or request.query_params:
            raise WebsiteError("Esta operación no admite datos de empresa o cliente.")
        return Response(start_session(request.user, hostname))


class CommercialProfileAPIView(CommercialAPIView):
    @extend_schema(tags=["Commercial accounts"], responses={200: CommercialProfileSerializer})
    def get(self, request, hostname):
        if request.query_params:
            raise WebsiteError("Consulta únicamente tu perfil actual.")
        _, user, website, account = resolve_session(request.auth, hostname)
        from apps.websites.order_requests import requests_enabled
        from apps.websites.registration import public_registration_policy
        return Response({
            "context": "commercial", "websiteId": str(website.pk),
            "accountId": str(account.pk),
            "company": {"name": website.company.name},
            "user": {"name": user.display_name, "email": user.email, "phone": user.phone},
            "contactVerified": True, "verificationChannel": "email",
            "wholesaleApproved": account.wholesale_approved_at is not None,
            "capabilities": {"catalog": True, "prepareOrders": requests_enabled(hostname), "registration": public_registration_policy(hostname)["registrationEnabled"]},
        })


def account_etag(account):
    digest = hashlib.sha256(f"{account.pk}:{account.updated_at.isoformat()}".encode()).hexdigest()
    return f'"account-{digest}"'


def administrative_account_data(account):
    user = account.user
    verified = account.verified_at is not None and account.verified_at >= user.updated_at and account.verified_email == user.email.strip().lower()
    profile = SalesCustomerProfile.objects.filter(customer_id=account.customer_id, active=True, price_list__company_id=account.company_id).select_related("price_list").first()
    price_list = profile.price_list if profile else None
    return {
        "id": str(account.pk), "status": account.status, "etag": account_etag(account),
        "user": {"name": user.display_name, "email": user.email},
        "customer": {"id": str(account.customer_id), "name": account.customer.legal_name},
        "contactVerified": verified, "wholesaleApproved": account.wholesale_approved_at is not None,
        "priceList": {"id": str(price_list.pk), "name": price_list.name, "active": price_list.active} if price_list else None,
    }


class AdministrativeAccountsAPIView(WebsiteAPIView):
    def scoped_accounts(self, website_id):
        website, _ = authorized_website(**self.context(), website_id=website_id, operation="policy")
        return CommercialAccount.objects.filter(company_id=website.company_id, customer__company_id=website.company_id).select_related("user", "customer")

    @extend_schema(operation_id="commercial_accounts_list", tags=["Commercial accounts administration"], parameters=[OpenApiParameter("search", str), OpenApiParameter("limit", int), OpenApiParameter("offset", int)], responses={200: AdministrativeAccountsPageSerializer})
    def get(self, request, website_id):
        query = query_values(request, SearchPageQuerySerializer)
        accounts = self.scoped_accounts(website_id)
        if query.get("search"):
            accounts = accounts.filter(Q(user__email__icontains=query["search"]) | Q(user__name__icontains=query["search"]) | Q(customer__legal_name__icontains=query["search"]))
        limit, offset = query["limit"], query["offset"]
        return Response({"websiteId": str(website_id), "count": accounts.count(), "limit": limit, "offset": offset, "results": [administrative_account_data(row) for row in accounts.order_by("user__email", "pk")[offset:offset + limit]]})


class AdministrativeAccountAPIView(AdministrativeAccountsAPIView):
    @extend_schema(operation_id="commercial_account_approval_update", tags=["Commercial accounts administration"], request=WholesaleApprovalSerializer, parameters=[OpenApiParameter("If-Match", str, location=OpenApiParameter.HEADER, required=True)], responses={200: AdministrativeAccountSerializer})
    @transaction.atomic
    def patch(self, request, website_id, account_id):
        account = get_object_or_404(self.scoped_accounts(website_id).select_for_update(of=("self",)), pk=account_id)
        expected = request.headers.get("If-Match")
        if expected is None:
            raise WebsiteError("Recarga la cuenta antes de modificarla.", code="PRECONDITION_REQUIRED", status=428)
        if expected != account_etag(account):
            raise WebsiteError("La cuenta cambió. Recarga antes de continuar.", code="ACCOUNT_CONFLICT", status=412)
        serializer = WholesaleApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = set_wholesale_approval(**self.context(), account_id=account.pk, approved=serializer.validated_data["wholesaleApproved"])
        return Response(administrative_account_data(account), headers={"ETag": account_etag(account)})

    @extend_schema(operation_id="commercial_account_retrieve", tags=["Commercial accounts administration"], responses={200: AdministrativeAccountSerializer})
    def get(self, request, website_id, account_id):
        account = get_object_or_404(self.scoped_accounts(website_id), pk=account_id)
        return Response(administrative_account_data(account), headers={"ETag": account_etag(account)})
