import re

from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import exceptions, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.authentication import JWTAuthentication
from apps.websites import media_storage, services
from apps.websites.errors import WebsiteError
from apps.websites.models import WebsiteMedia, WebsitePageRevision, WebsiteDomain, normalize_hostname
from apps.websites.public_content import published_content
from django.core.exceptions import ValidationError
from apps.websites.permissions import WebsiteAccessDenied, website_capabilities, require_website_permission
from apps.websites.selectors import get_company_website

from .parsers import WebsiteJSONParser, WebsiteMultipartParser
from .serializers import (
    PublicWebsiteContextSerializer, PublicWebsiteContentSerializer, CurrentWebsiteSerializer, EditorRecordSerializer, MediaPageSerializer,
    RestoreRevisionSerializer, RevisionsPageSerializer, SaveDraftSerializer,
    UploadMediaSerializer, WebsiteMediaSerializer, WebsitePreviewSerializer,
)


REVISION_HEADER = OpenApiParameter(
    name="If-Match", type=str, location=OpenApiParameter.HEADER, required=True,
    description='Strong ETag of the entire website, for example "4".',
)
ETAG_RESPONSE_HEADER = OpenApiParameter(
    name="ETag", type=str, location=OpenApiParameter.HEADER, response=[200],
    description="Current revision of the complete editorial aggregate.",
)


class WebsiteJWTAuthentication(JWTAuthentication):
    """Keep existing JWT verification; add a challenge only for the new API."""

    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except UnicodeDecodeError as exc:
            raise exceptions.AuthenticationFailed("Credencial inv?lida.") from exc


def error_fields(value, prefix=""):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            result.update(error_fields(item, f"{prefix}.{key}" if prefix else key))
        return result
    if isinstance(value, list):
        return {prefix: "; ".join(map(str, value))}
    return {prefix: str(value)}


class WebsiteAPIView(APIView):
    authentication_classes = [WebsiteJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [WebsiteJSONParser]

    def context(self):
        claims = self.request.auth if isinstance(self.request.auth, dict) else {}
        return {"user": self.request.user, "company_id": claims.get("company_id"), "store_id": claims.get("store_id")}

    def website(self, website_id, permission="view"):
        context = self.context()
        website = get_company_website(**context, website_id=website_id)
        require_website_permission(**context, permission=permission)
        return website

    def expected_revision(self):
        value = self.request.headers.get("If-Match")
        if value is None:
            raise WebsiteError("If-Match es obligatorio.", code="PRECONDITION_REQUIRED", status=428)
        if not re.fullmatch(r'"(?:0|[1-9][0-9]{0,19})"', value):
            raise WebsiteError("Usa un ETag fuerte con la revisi?n entre comillas.")
        return int(value[1:-1])

    def record_response(self, record):
        return Response(record, headers={"ETag": f'"{record["revision"]}"'})

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    def handle_exception(self, exc):
        if isinstance(exc, WebsiteError):
            return Response({"code": exc.code, "message": str(exc), **({"fields": exc.fields} if exc.fields else {})}, status=exc.status)
        if isinstance(exc, WebsiteAccessDenied):
            exc = exceptions.PermissionDenied(str(exc), code=exc.code)
        if isinstance(exc, ObjectDoesNotExist):
            exc = Http404("Recurso no encontrado.")
        response = super().handle_exception(exc)
        codes = {400: "VALIDATION", 401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 413: "PAYLOAD_TOO_LARGE", 415: "UNSUPPORTED_MEDIA_TYPE"}
        code = "COMPANY_REQUIRED" if getattr(exc, "get_codes", lambda: None)() == "COMPANY_REQUIRED" else codes.get(response.status_code, "API_ERROR")
        data = response.data
        response.data = {"code": code, "message": str(data.get("detail", "Revisa los campos indicados."))}
        if "detail" not in data:
            response.data["fields"] = error_fields(data)
        return response


class WebsiteReadOnlyAPIView(WebsiteAPIView):
    http_method_names = ["get", "head", "options"]


class CurrentWebsiteAPIView(WebsiteReadOnlyAPIView):
    @extend_schema(tags=["Websites"], summary="Discover the active company's website", responses=CurrentWebsiteSerializer)
    def get(self, request):
        context = self.context()
        _, capabilities = website_capabilities(**context)
        website = get_company_website(**context)
        hostname = request.query_params.get("hostname")
        if hostname:
            try:
                domain = normalize_hostname(hostname)
            except ValidationError:
                domain = None
            if domain and WebsiteDomain.objects.filter(hostname=domain).exclude(website=website).exists():
                raise WebsiteError("El dominio pertenece a otra empresa. Cambia de empresa o abre la administración central.", code="DOMAIN_COMPANY_MISMATCH", status=403)
        return Response(CurrentWebsiteSerializer({
            "id": website.id, "company_id": website.company_id,
            "template_key": website.template_key, "documentSchemaVersion": 3,
            "editorial_revision": website.editorial_revision, "capabilities": capabilities,
        }).data)


class WebsiteEditorAPIView(WebsiteReadOnlyAPIView):
    @extend_schema(tags=["Websites"], parameters=[ETAG_RESPONSE_HEADER], summary="Read complete editorial draft and published snapshot", responses=EditorRecordSerializer)
    def get(self, request, website_id):
        return self.record_response(services.load_editor(**self.context(), website_id=website_id))


class WebsiteDraftAPIView(WebsiteAPIView):
    http_method_names = ["put", "options"]

    @extend_schema(tags=["Websites"], parameters=[REVISION_HEADER, ETAG_RESPONSE_HEADER], request=SaveDraftSerializer, responses=EditorRecordSerializer)
    def put(self, request, website_id):
        self.website(website_id, "edit")
        expected = self.expected_revision()
        serializer = SaveDraftSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = services.save_draft(**self.context(), website_id=website_id, expected_revision=expected, document=serializer.validated_data["document"], media_references=serializer.validated_data.get("mediaReferences"))
        return self.record_response(record)


class WebsitePublishAPIView(WebsiteAPIView):
    http_method_names = ["post", "options"]

    @extend_schema(tags=["Websites"], parameters=[REVISION_HEADER, ETAG_RESPONSE_HEADER], request=None, responses=EditorRecordSerializer)
    def post(self, request, website_id):
        self.website(website_id, "publish")
        expected = self.expected_revision()
        if request.data not in ({}, None):
            raise WebsiteError("Publicar solo admite el borrador guardado, sin body.")
        return self.record_response(services.publish_website(**self.context(), website_id=website_id, expected_revision=expected))


def page_results(queryset, request, serialize):
    try:
        limit, offset = int(request.query_params.get("limit", 20)), int(request.query_params.get("offset", 0))
        if not 1 <= limit <= 100 or not 0 <= offset <= 2**63 - 1:
            raise ValueError
    except (ValueError, TypeError):
        raise WebsiteError("Paginaci?n inv?lida: limit 1?100, offset >= 0.")
    return {"count": queryset.count(), "results": [serialize(item) for item in queryset[offset:offset + limit]]}


class WebsiteRevisionsAPIView(WebsiteReadOnlyAPIView):
    @extend_schema(tags=["Websites"], responses=RevisionsPageSerializer)
    def get(self, request, website_id):
        website = self.website(website_id)
        queryset = WebsitePageRevision.objects.filter(page__website=website, page__page_type="HOME").select_related("created_by").order_by("-version")

        def summary(item):
            return {"id": str(item.id), "version": item.version, "editorialRevision": item.editorial_revision, "operation": item.operation, "at": item.created_at, "actor": {"id": str(item.created_by_id), "name": item.created_by.display_name} if item.created_by_id else None, "sourceRevisionId": str(item.source_revision_id) if item.source_revision_id else None}

        return Response(page_results(queryset, request, summary))


class WebsiteRestoreAPIView(WebsiteAPIView):
    http_method_names = ["post", "options"]

    @extend_schema(tags=["Websites"], parameters=[REVISION_HEADER, ETAG_RESPONSE_HEADER], request=RestoreRevisionSerializer, responses=EditorRecordSerializer)
    def post(self, request, website_id):
        self.website(website_id, "edit")
        expected = self.expected_revision()
        serializer = RestoreRevisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.record_response(services.restore_revision(**self.context(), website_id=website_id, revision_id=serializer.validated_data["revisionId"], expected_revision=expected))


class WebsitePreviewAPIView(WebsiteReadOnlyAPIView):
    @extend_schema(tags=["Websites"], parameters=[ETAG_RESPONSE_HEADER], responses=WebsitePreviewSerializer)
    def get(self, request, website_id):
        record = services.load_editor(**self.context(), website_id=website_id)
        return Response({"websiteId": record["websiteId"], "revision": record["revision"], "content": record["draft"]}, headers={"ETag": f'"{record["revision"]}"', "X-Robots-Tag": "noindex, nofollow"})


class WebsiteMediaAPIView(WebsiteAPIView):
    http_method_names = ["get", "post", "head", "options"]
    parser_classes = [WebsiteMultipartParser]

    @extend_schema(tags=["Websites"], responses=MediaPageSerializer)
    def get(self, request, website_id):
        website = self.website(website_id)
        queryset = WebsiteMedia.objects.filter(website=website, is_deleted=False).order_by("-created_at", "-pk")
        return Response(page_results(queryset, request, lambda item: WebsiteMediaSerializer(item).data))

    @extend_schema(tags=["Websites"], request=UploadMediaSerializer, responses={201: WebsiteMediaSerializer, 200: WebsiteMediaSerializer})
    def post(self, request, website_id):
        self.website(website_id, "mediaUpload")
        serializer = UploadMediaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        media, created = media_storage.upload_media(**self.context(), website_id=website_id, uploaded_file=serializer.validated_data["file"], kind=serializer.validated_data["kind"], alt_text=serializer.validated_data["altText"])
        return Response(WebsiteMediaSerializer(media).data, status=201 if created else 200)


class WebsiteMediaDetailAPIView(WebsiteAPIView):
    http_method_names = ["delete", "options"]

    @extend_schema(tags=["Websites"], responses={204: None})
    def delete(self, request, website_id, media_id):
        media_storage.deactivate_media(**self.context(), website_id=website_id, media_id=media_id)
        return Response(status=204)


class PublicWebsiteAPIView(WebsiteReadOnlyAPIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["Storefront"], auth=[], responses=PublicWebsiteContentSerializer)
    def get(self, request, hostname=None):
        data = published_content(hostname if hostname is not None else request.query_params.get("hostname", ""))
        return Response(data)


class PublicWebsiteResolveAPIView(PublicWebsiteAPIView):
    @extend_schema(tags=["Storefront"], auth=[], parameters=[OpenApiParameter(name="hostname", type=str, required=True)], responses=PublicWebsiteContextSerializer)
    def get(self, request):
        data = published_content(request.query_params.get("hostname", ""))
        return Response({key: data[key] for key in ("websiteId", "hostname", "canonicalHostname", "templateKey", "locale", "currency", "revision")})
