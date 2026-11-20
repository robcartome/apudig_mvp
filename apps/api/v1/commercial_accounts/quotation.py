import secrets
from rest_framework import serializers
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes

from apps.api.v1.websites.serializers import StrictSerializer
from apps.websites.catalog.quotation import recalculate_commercial_cart
from apps.websites.commercial_sessions import resolve_session
from apps.websites.errors import WebsiteError
from apps.websites.order_requests import requests_enabled
from .views import CommercialAPIView


class CartReviewSerializer(StrictSerializer):
    # Domain validation rejects unknown fields, booleans/floats and duplicate
    # product/unit pairs before any ERP offer is calculated.
    items = serializers.ListField(child=serializers.DictField(), min_length=1, max_length=200)


class CartConfirmationSerializer(CartReviewSerializer):
    offerFingerprint = serializers.RegexField(r"^[0-9a-f]{64}$")


class CommercialCartQuoteAPIView(CommercialAPIView):
    @extend_schema(tags=["Commercial cart"], request=CartReviewSerializer, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, hostname):
        resolve_session(request.auth, hostname)
        serializer = CartReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quote = recalculate_commercial_cart(request.user, hostname, serializer.validated_data["items"])
        return Response({**quote, "confirmed": False, "ordersEnabled": requests_enabled(hostname)})


class CommercialCartConfirmAPIView(CommercialAPIView):
    @extend_schema(tags=["Commercial cart"], request=CartConfirmationSerializer, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, hostname):
        resolve_session(request.auth, hostname)
        serializer = CartConfirmationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        quote = recalculate_commercial_cart(request.user, hostname, data["items"])
        if not secrets.compare_digest(quote["offerFingerprint"], data["offerFingerprint"]):
            raise WebsiteError("La oferta cambió. Calcula y revisa el resumen actualizado.", code="OFFER_CHANGED", status=409)
        return Response({**quote, "confirmed": True, "ordersEnabled": requests_enabled(hostname)})
