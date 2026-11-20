import hashlib
from django.db import connection
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes

from apps.api.v1.websites.views import WebsiteAPIView
from apps.api.v1.websites.serializers import StrictSerializer
from apps.api.v1.website_catalog.views import query_values
from apps.api.v1.website_catalog.serializers import SearchPageQuerySerializer
from apps.websites import registration as services
from apps.websites.catalog.services import authorized_website
from apps.websites.errors import WebsiteError
from apps.websites.models import CommercialRegistration, WebsiteRegistrationPolicy
from apps.partners.models import Customer
from .authentication import CommercialIdentityAuthentication
from apps.websites.registration_limits import client_address, consume_budget


class RegistrationStartSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)
    name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    noticeVersion = serializers.CharField(max_length=40)
    consent = serializers.BooleanField()
    purpose = serializers.ChoiceField(choices=("REGISTER", "RECOVERY"), default="REGISTER")

    def validate_consent(self, value):
        if self.initial_data.get("consent") is not True:
            raise serializers.ValidationError("Acepta el aviso vigente.")
        return value


class RegistrationCompleteSerializer(StrictSerializer):
    token = serializers.CharField(max_length=100, trim_whitespace=False)
    password = serializers.CharField(max_length=200, required=False, default="", trim_whitespace=False)
    purpose = serializers.ChoiceField(choices=("REGISTER", "RECOVERY"), default="REGISTER")


class NoticeSerializer(StrictSerializer):
    version = serializers.CharField(max_length=40)
    text = serializers.CharField(max_length=15000)
    pendingRetentionDays = serializers.IntegerField(min_value=1, max_value=36500)
    linkingMode = serializers.ChoiceField(choices=("REVIEW_ALL", "NEW_OR_REVIEW"))


class RegistrationReviewSerializer(StrictSerializer):
    customerId = serializers.UUIDField()


class RegistrationThrottle(SimpleRateThrottle):
    scope = "website_registration"
    rate = "20/hour"

    def get_cache_key(self, request, view):
        # Same explicit trusted-proxy policy as the authoritative DB budgets.
        # This process-local throttle is only an additional early limit.
        identity = client_address(request.META) + ":" + view.kwargs.get("hostname", "")
        return self.cache_format % {"scope": self.scope, "ident": hashlib.sha256(identity.encode()).hexdigest()}


class RegistrationPolicyAPIView(WebsiteAPIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["Commercial registration"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request, hostname):
        return Response(services.public_registration_policy(hostname))


class RegistrationStartAPIView(RegistrationPolicyAPIView):
    throttle_classes = [RegistrationThrottle]

    @extend_schema(tags=["Commercial registration"], request=RegistrationStartSerializer, responses={202: OpenApiTypes.OBJECT})
    def post(self, request, hostname):
        serializer = RegistrationStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.start_registration(hostname, email=data["email"], name=data["name"], notice_version=data["noticeVersion"], consent=data["consent"], purpose=data["purpose"], origin=client_address(request.META))
        return Response({"message": "Si la solicitud puede tramitarse, recibirás las instrucciones por correo."}, status=202)

    http_method_names = ["post", "options"]


class RegistrationCompleteAPIView(WebsiteAPIView):
    authentication_classes = [CommercialIdentityAuthentication]
    permission_classes = [permissions.AllowAny]
    throttle_classes = [RegistrationThrottle]

    @extend_schema(tags=["Commercial registration"], request=RegistrationCompleteSerializer, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, hostname):
        serializer = RegistrationCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.require_registration(hostname)
        consume_budget(hostname, "", client_address(request.META), proof=True)
        if data["purpose"] == "RECOVERY":
            services.recover_password(hostname, secret=data["token"], password=data["password"])
            return Response({"status": "COMPLETE"})
        return Response(services.complete_registration(hostname, secret=data["token"], password=data["password"], identity=request.user if request.user.is_authenticated else None))


def require_registration_schema():
    if WebsiteRegistrationPolicy._meta.db_table not in connection.introspection.table_names():
        raise WebsiteError("La configuración de registro aún no está disponible.", code="REGISTRATION_UNAVAILABLE", status=503)


class AdministrativeRegistrationPolicyAPIView(WebsiteAPIView):
    @extend_schema(tags=["Commercial registration administration"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request, website_id):
        website, _ = authorized_website(**self.context(), website_id=website_id, operation="policy")
        require_registration_schema()
        policy = services.policy_for(website)
        return Response({"notice": {"version": policy.notice.version, "text": policy.notice.text, "pendingRetentionDays": policy.notice.pending_retention_days, "linkingMode": policy.linking_mode} if policy else None, "etag": services.policy_etag(policy), "publicRegistrationEnabled": services.registration_enabled(policy)}, headers={"ETag": services.policy_etag(policy)})

    @extend_schema(tags=["Commercial registration administration"], request=NoticeSerializer, responses={201: OpenApiTypes.OBJECT})
    def post(self, request, website_id):
        require_registration_schema()
        serializer = NoticeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        notice = services.configure_notice(**self.context(), website_id=website_id, version=data["version"], text=data["text"], pending_retention_days=data["pendingRetentionDays"], linking_mode=data["linkingMode"], expected=request.headers.get("If-Match"))
        return Response({"version": notice.version, "publicRegistrationEnabled": services.registration_enabled(services.policy_for(notice.website))}, status=201)


class AdministrativeRegistrationsAPIView(WebsiteAPIView):
    @extend_schema(tags=["Commercial registration administration"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request, website_id):
        website, _ = authorized_website(**self.context(), website_id=website_id, operation="policy")
        require_registration_schema()
        query = query_values(request, SearchPageQuerySerializer)
        rows = CommercialRegistration.objects.filter(website=website, status="REVIEW").order_by("created_at", "pk")
        if query.get("search"):
            rows = rows.filter(email__icontains=query["search"])
        limit, offset = query["limit"], query["offset"]
        return Response({"count": rows.count(), "results": [{"id": str(row.pk), "name": row.name, "email": row.email, "verifiedAt": row.verified_at} for row in rows[offset:offset + limit]]})


class AdministrativeRegistrationReviewAPIView(WebsiteAPIView):
    @extend_schema(tags=["Commercial registration administration"], request=RegistrationReviewSerializer, responses={204: None})
    def post(self, request, website_id, registration_id):
        serializer = RegistrationReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.review_registration(**self.context(), website_id=website_id, registration_id=registration_id, customer_id=serializer.validated_data["customerId"])
        return Response(status=204)


class RegistrationCustomerOptionsAPIView(WebsiteAPIView):
    @extend_schema(tags=["Commercial registration administration"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request, website_id):
        website, _ = authorized_website(**self.context(), website_id=website_id, operation="policy")
        query = query_values(request, SearchPageQuerySerializer)
        rows = Customer.objects.filter(company=website.company, active=True)
        if query.get("search"):
            from django.db.models import Q
            rows = rows.filter(Q(legal_name__icontains=query["search"]) | Q(document_number__icontains=query["search"]))
        limit, offset = query["limit"], query["offset"]
        return Response({"count": rows.count(), "results": [{"id": str(row.pk), "name": row.legal_name, "documentNumber": row.document_number} for row in rows.order_by("legal_name", "pk")[offset:offset + limit]]})
