from django.db import connection, transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from apps.api.v1.websites.serializers import StrictSerializer
from apps.api.v1.website_catalog.serializers import PageQuerySerializer
from apps.api.v1.website_catalog.views import query_values
from apps.websites.commercial_sessions import resolve_session
from apps.websites.models import CommercialOrderRequest, Website
from apps.websites.models import CommercialConsent
from apps.websites.registration import policy_for
from django.utils import timezone
from apps.core.models import AuditLog
from apps.websites.errors import WebsiteError
from apps.websites import order_requests as services
from .quotation import CartConfirmationSerializer
from .views import CommercialAPIView


class OrderPreparationSerializer(CartConfirmationSerializer):
    note = serializers.CharField(max_length=500, allow_blank=True, default="")
    shareConfirmed = serializers.BooleanField()

    def validate_shareConfirmed(self, value):
        if self.initial_data.get("shareConfirmed") is not True:
            raise serializers.ValidationError("Confirma expresamente esta acción.")
        return value


def require_request_schema():
    if CommercialOrderRequest._meta.db_table not in connection.introspection.table_names():
        raise WebsiteError("Las solicitudes todavía no están disponibles.", code="REQUESTS_UNAVAILABLE", status=503)


class OrderRequestsAPIView(CommercialAPIView):
    @extend_schema(operation_id="commercial_order_requests_list", tags=["Commercial requests"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request, hostname):
        resolve_session(request.auth, hostname)
        require_request_schema()
        query = query_values(request, PageQuerySerializer)
        rows = services.owned_requests(request.user, hostname).order_by("-created_at", "-pk")
        limit, offset = query["limit"], query["offset"]
        return Response({"websiteId": request.auth["website_id"], "ordersEnabled": services.requests_enabled(hostname), "count": rows.count(), "limit": limit, "offset": offset, "results": [services.request_data(row) for row in rows[offset:offset + limit]]})

    @extend_schema(tags=["Commercial requests"], request=OrderPreparationSerializer, parameters=[OpenApiParameter("Idempotency-Key", str, location=OpenApiParameter.HEADER, required=True)], responses={201: OpenApiTypes.OBJECT})
    @transaction.atomic
    def post(self, request, hostname):
        _, _, website, _ = resolve_session(request.auth, hostname)
        Website.objects.select_for_update().get(pk=website.pk)
        if not services.requests_enabled(hostname):
            raise WebsiteError("Los pedidos aún no están habilitados.", code="COMMERCE_DISABLED", status=403)
        require_request_schema()
        serializer = OrderPreparationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        row = services.prepare_request(user=request.user, hostname=hostname, items=data["items"], offer_fingerprint=data["offerFingerprint"], note=data["note"], idempotency_key=request.headers.get("Idempotency-Key"), share_confirmed=data["shareConfirmed"])
        return Response({"websiteId": request.auth["website_id"], **services.request_data(row, allow_whatsapp=True)}, status=201)


class OrderRequestDetailAPIView(CommercialAPIView):
    @extend_schema(operation_id="commercial_order_request_retrieve", tags=["Commercial requests"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request, hostname, request_id):
        resolve_session(request.auth, hostname)
        require_request_schema()
        row = get_object_or_404(services.owned_requests(request.user, hostname), pk=request_id)
        return Response({"websiteId": request.auth["website_id"], **services.current_request_data(row, request.user, hostname)})


class CancelOrderRequestAPIView(CommercialAPIView):
    @extend_schema(tags=["Commercial requests"], request=None, responses={200: OpenApiTypes.OBJECT})
    @transaction.atomic
    def post(self, request, hostname, request_id):
        resolve_session(request.auth, hostname)
        require_request_schema()
        if request.data:
            raise WebsiteError("Cancelar no admite cambios al contenido.")
        row = get_object_or_404(services.owned_requests(request.user, hostname).select_for_update(), pk=request_id)
        if services.effective_status(row) == "EXPIRED":
            raise WebsiteError("La solicitud ya caducó.", code="REQUEST_EXPIRED", status=409)
        if row.status != "CANCELLED":
            row.status = "CANCELLED"
            row.save(update_fields=["status"])
            AuditLog.objects.create(user=request.user, action="COMMERCIAL_REQUEST_CANCELLED", entity="CommercialOrderRequest", entity_id=str(row.pk), meta_data={"websiteId": str(row.website_id)})
        return Response({"websiteId": request.auth["website_id"], **services.request_data(row)})


class AccountConsentSerializer(StrictSerializer):
    noticeVersion = serializers.CharField(max_length=40)
    accepted = serializers.BooleanField()

    def validate_accepted(self, value):
        if self.initial_data.get("accepted") is not True:
            raise serializers.ValidationError("Debes aceptar expresamente el aviso.")
        return value


class AccountPrivacyAPIView(CommercialAPIView):
    def notice(self, request, hostname):
        _, _, website, _ = resolve_session(request.auth, hostname)
        # Same lock order as changing the notice and preparing a request.
        if connection.in_atomic_block:
            Website.objects.select_for_update().get(pk=website.pk)
        policy = policy_for(website)
        if policy is None:
            raise WebsiteError("El aviso no está disponible todavía.", code="PRIVACY_UNAVAILABLE", status=503)
        return website, policy.notice

    @extend_schema(tags=["Commercial privacy"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request, hostname):
        website, notice = self.notice(request, hostname)
        return Response({"websiteId": str(website.pk), "version": notice.version, "text": notice.text, "accepted": CommercialConsent.objects.filter(user=request.user, notice=notice).exists()})

    @extend_schema(tags=["Commercial privacy"], request=AccountConsentSerializer, responses={200: OpenApiTypes.OBJECT})
    @transaction.atomic
    def post(self, request, hostname):
        website, notice = self.notice(request, hostname)
        serializer = AccountConsentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["noticeVersion"] != notice.version:
            raise WebsiteError("El aviso cambió. Revisa su versión vigente.", code="NOTICE_CHANGED", status=409)
        CommercialConsent.objects.get_or_create(user=request.user, notice=notice, defaults={"accepted_at": timezone.now()})
        return Response({"websiteId": str(website.pk), "accepted": True, "version": notice.version})
