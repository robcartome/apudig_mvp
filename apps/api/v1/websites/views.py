from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.core import signing
from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.exceptions import PermissionDenied
from django.conf import settings

from apps.api.v1.base import BaseCompanyAPIView
from apps.api.v1.permissions import HasCompanyPermission
from apps.api.v1.websites.serializers import (
    WebsiteDomainSerializer,
    WebsiteSerializer,
    WebsiteSettingsSerializer,
    WebsitePageSerializer,
    ReplaceSectionsSerializer,
    PublishPageSerializer,
    WebsiteMediaSerializer,
    WebsiteMediaUploadSerializer,
    WebsiteMenuSerializer,
    ReplaceMenuItemsSerializer,
    PublishMenuSerializer,
    WebsiteCatalogSettingsSerializer,
    WebsiteProductSerializer,
    WebsiteCatalogProductOptionSerializer,
)
from apps.websites.models import Website, WebsiteCatalogSettings, WebsiteDomain, WebsiteMedia, WebsiteMenu, WebsitePage, WebsitePageRevision, WebsiteProduct, WebsiteSettings, normalize_hostname
from apps.websites.selectors import get_company_website, get_public_website_by_hostname, get_published_page_by_hostname
from apps.websites.media_storage import create_website_media
from apps.inventory.product_image_storage import ProductImageStorageError
from apps.inventory.models import Product
from apps.users.permissions import user_has_company_permission
from apps.websites.services import (
    MenuVersionConflict, PageVersionConflict, build_page_snapshot, create_preview_token,
    issue_domain_verification_token, publish_page, read_preview_token,
    replace_page_sections, replace_menu_items, publish_menu,
    restore_page_revision,
    send_website_revalidation,
)


class WebsitePermissionMixin:
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    company_required = True
    required_company_permissions = {}

    def get_required_company_permission(self):
        return self.required_company_permissions.get(
            self.request.method,
            "manage.website",
        )

    def get_website(self):
        try:
            return get_company_website(self.get_required_company_id())
        except Website.DoesNotExist as exc:
            raise Http404("La empresa activa no tiene un sitio web configurado.") from exc


class CurrentWebsiteAPIView(WebsitePermissionMixin, BaseCompanyAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = WebsiteSerializer
    required_company_permissions = {
        "GET": "read.website",
        "PATCH": "manage.website",
        "PUT": "manage.website",
    }

    def get_object(self):
        return self.get_website()

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @extend_schema(tags=["Websites CMS"], summary="Get the website for the active company")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(tags=["Websites CMS"], summary="Update basic website settings")
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)


class CurrentWebsiteDomainContextAPIView(WebsitePermissionMixin, BaseCompanyAPIView, generics.GenericAPIView):
    required_company_permissions = {"GET": "read.website"}

    def get(self, request):
        hostname = request.query_params.get("hostname", "")
        try:
            normalized = normalize_hostname(hostname)
        except DjangoValidationError as exc:
            raise Http404 from exc
        domain = WebsiteDomain.objects.filter(
            hostname=normalized,
            status=WebsiteDomain.Status.ACTIVE,
            verified_at__isnull=False,
            website=self.get_website(),
        ).first()
        if not domain:
            raise Http404("El dominio no pertenece a la empresa activa.")
        return Response({"website_id": str(domain.website_id), "hostname": domain.hostname})


class CurrentWebsiteDomainListCreateAPIView(
    WebsitePermissionMixin,
    BaseCompanyAPIView,
    generics.ListCreateAPIView,
):
    serializer_class = WebsiteDomainSerializer
    required_company_permissions = {
        "GET": "read.website",
        "POST": "manage.website.domains",
    }

    def get_queryset(self):
        return WebsiteDomain.objects.filter(website=self.get_website()).order_by(
            "-is_primary", "hostname"
        )

    @extend_schema(tags=["Websites CMS"], summary="List domains for the active website")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(tags=["Websites CMS"], summary="Register a pending website domain")
    def post(self, request, *args, **kwargs):
        hostname = request.data.get("hostname", "")
        try:
            normalized = normalize_hostname(hostname)
        except DjangoValidationError:  # The serializer returns the field-level detail.
            normalized = hostname
        if WebsiteDomain.objects.filter(hostname__iexact=normalized).exists():
            return Response(
                {"code": "DOMAIN_CONFLICT", "detail": "El dominio ya estÃ¡ registrado."},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            return super().post(request, *args, **kwargs)
        except (DjangoValidationError, IntegrityError):
            if not WebsiteDomain.objects.filter(hostname__iexact=normalized).exists():
                raise
            return Response(
                {"code": "DOMAIN_CONFLICT", "detail": "El dominio ya estÃ¡ registrado."},
                status=status.HTTP_409_CONFLICT,
            )

    def perform_create(self, serializer):
        with transaction.atomic():
            domain = serializer.save(
                website=self.get_website(),
                status=WebsiteDomain.Status.PENDING,
                is_primary=False,
            )
            domain._verification_token = issue_domain_verification_token(domain)


class CurrentWebsiteSettingsAPIView(
    WebsitePermissionMixin,
    BaseCompanyAPIView,
    generics.RetrieveUpdateAPIView,
):
    serializer_class = WebsiteSettingsSerializer
    required_company_permissions = {
        "GET": "read.website",
        "PATCH": "manage.website",
        "PUT": "manage.website",
    }

    def get_object(self):
        website = self.get_website()
        settings_object, _ = WebsiteSettings.objects.get_or_create(
            website=website,
            defaults={"business_name": website.name},
        )
        return settings_object

    @extend_schema(tags=["Websites CMS"], summary="Get public identity settings")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(tags=["Websites CMS"], summary="Update public identity settings")
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)


class CurrentWebsiteCatalogSettingsAPIView(
    WebsitePermissionMixin,
    BaseCompanyAPIView,
    generics.RetrieveUpdateAPIView,
):
    serializer_class = WebsiteCatalogSettingsSerializer
    required_company_permissions = {
        "GET": "read.website",
        "PATCH": "manage.website",
        "PUT": "manage.website",
    }

    def get_object(self):
        settings_object, _ = WebsiteCatalogSettings.objects.get_or_create(
            website=self.get_website()
        )
        return settings_object

    def perform_update(self, serializer):
        catalog_settings = serializer.save()
        transaction.on_commit(
            lambda: send_website_revalidation(catalog_settings.website)
        )


class CurrentWebsiteProductListCreateAPIView(
    WebsitePermissionMixin,
    BaseCompanyAPIView,
    generics.ListCreateAPIView,
):
    serializer_class = WebsiteProductSerializer
    required_company_permissions = {"GET": "read.website", "POST": "manage.website"}
    pagination_class = None

    def get_queryset(self):
        return WebsiteProduct.objects.filter(website=self.get_website()).select_related(
            "product__category", "product__brand", "price_list"
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["website"] = self.get_website()
        return context

    def perform_create(self, serializer):
        if serializer.validated_data.get("is_published") and not user_has_company_permission(
            self.request.user, self.get_required_company_id(), "publish.website"
        ):
            raise PermissionDenied("No tiene permiso para publicar productos del sitio.")
        publication = serializer.save(website=self.get_website())
        transaction.on_commit(lambda: send_website_revalidation(publication.website))


class CurrentWebsiteProductDetailAPIView(
    WebsitePermissionMixin,
    BaseCompanyAPIView,
    generics.RetrieveUpdateDestroyAPIView,
):
    serializer_class = WebsiteProductSerializer
    http_method_names = ("get", "patch", "delete", "head", "options")
    required_company_permissions = {
        "GET": "read.website",
        "PATCH": "manage.website",
        "DELETE": "manage.website",
    }

    def get_queryset(self):
        return WebsiteProduct.objects.filter(website=self.get_website()).select_related(
            "product__category", "product__brand", "price_list"
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["website"] = self.get_website()
        return context

    def perform_update(self, serializer):
        requested_status = serializer.validated_data.get("is_published", serializer.instance.is_published)
        if requested_status != serializer.instance.is_published and not user_has_company_permission(
            self.request.user, self.get_required_company_id(), "publish.website"
        ):
            raise PermissionDenied("No tiene permiso para cambiar la publicación del producto.")
        publication = serializer.save()
        transaction.on_commit(lambda: send_website_revalidation(publication.website))

    def perform_destroy(self, instance):
        website = instance.website
        instance.delete()
        transaction.on_commit(lambda: send_website_revalidation(website))


class CurrentWebsiteCatalogProductOptionsAPIView(
    WebsitePermissionMixin,
    BaseCompanyAPIView,
    generics.ListAPIView,
):
    serializer_class = WebsiteCatalogProductOptionSerializer
    required_company_permissions = {"GET": "read.website"}
    pagination_class = None

    def get_queryset(self):
        search = (self.request.query_params.get("search") or "").strip()
        queryset = Product.objects.filter(
            company_id=self.get_website().company_id, active=True
        ).select_related("category", "brand").order_by("name")
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(sku__icontains=search))
        return queryset[:200]


class CurrentWebsitePageListCreateAPIView(WebsitePermissionMixin, BaseCompanyAPIView, generics.ListCreateAPIView):
    serializer_class = WebsitePageSerializer
    required_company_permissions = {"GET": "read.website", "POST": "manage.website"}

    def get_queryset(self):
        return WebsitePage.objects.filter(website=self.get_website()).prefetch_related("sections")

    def perform_create(self, serializer):
        website = self.get_website()
        slug = "home" if serializer.validated_data.get("page_type") == WebsitePage.PageType.HOME else serializer.validated_data["slug"]
        if WebsitePage.objects.filter(website=website, slug=slug).exists():
            raise DRFValidationError({"slug": "Ya existe una página con este slug."})
        serializer.save(website=website, created_by=self.request.user, updated_by=self.request.user)


class CurrentWebsitePageDetailAPIView(WebsitePermissionMixin, BaseCompanyAPIView, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = WebsitePageSerializer
    http_method_names = ("get", "patch", "delete", "head", "options")
    required_company_permissions = {"GET": "read.website", "PATCH": "manage.website", "DELETE": "manage.website"}

    def get_queryset(self):
        return WebsitePage.objects.filter(website=self.get_website()).prefetch_related("sections")

    def destroy(self, request, *args, **kwargs):
        page = self.get_object()
        if page.published_version:
            page.status = WebsitePage.Status.ARCHIVED
            page.draft_version += 1
            page.updated_by = request.user
            page.save()
        else:
            page.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentWebsitePageSectionsAPIView(WebsitePermissionMixin, BaseCompanyAPIView, generics.GenericAPIView):
    serializer_class = ReplaceSectionsSerializer
    required_company_permissions = {"PUT": "manage.website"}

    def get_page(self):
        try:
            return WebsitePage.objects.get(pk=self.kwargs["pk"], website=self.get_website())
        except WebsitePage.DoesNotExist as exc:
            raise Http404 from exc

    def put(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            page = replace_page_sections(
                page=self.get_page(), actor=request.user, **serializer.validated_data
            )
        except PageVersionConflict:
            return Response({"code": "VERSION_CONFLICT", "detail": "La página cambió desde que se abrió."}, status=status.HTTP_409_CONFLICT)
        except (DjangoValidationError, ValueError) as exc:
            return Response({"code": "INVALID_BLOCK", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        page.refresh_from_db()
        return Response(WebsitePageSerializer(page, context={"request": request}).data)


class CurrentWebsitePagePublishAPIView(WebsitePermissionMixin, BaseCompanyAPIView, generics.GenericAPIView):
    serializer_class = PublishPageSerializer
    required_company_permissions = {"POST": "publish.website"}

    def post(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            page = WebsitePage.objects.get(pk=pk, website=self.get_website())
            page, revision = publish_page(page=page, actor=request.user, **serializer.validated_data)
        except WebsitePage.DoesNotExist as exc:
            raise Http404 from exc
        except PageVersionConflict:
            return Response({"code": "VERSION_CONFLICT", "detail": "La página cambió desde que se abrió."}, status=status.HTTP_409_CONFLICT)
        except DjangoValidationError as exc:
            return Response({"code": "INVALID_BLOCK", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"page": WebsitePageSerializer(page, context={"request": request}).data, "revision": revision.version})


class CurrentWebsitePagePreviewTokenAPIView(WebsitePermissionMixin, BaseCompanyAPIView, generics.GenericAPIView):
    required_company_permissions = {"POST": "manage.website"}

    def post(self, request, pk):
        try:
            page = WebsitePage.objects.get(pk=pk, website=self.get_website())
        except WebsitePage.DoesNotExist as exc:
            raise Http404 from exc
        return Response({"token": create_preview_token(page), "expires_in": settings.WEBSITE_PREVIEW_TOKEN_TTL})


class CurrentWebsitePageRestoreAPIView(WebsitePermissionMixin, BaseCompanyAPIView, generics.GenericAPIView):
    serializer_class = PublishPageSerializer
    required_company_permissions = {"POST": "manage.website"}

    def post(self, request, pk, version):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            page = WebsitePage.objects.get(pk=pk, website=self.get_website())
            page = restore_page_revision(
                page=page, version=version, actor=request.user,
                expected_version=serializer.validated_data["expected_version"],
            )
        except (WebsitePage.DoesNotExist, WebsitePageRevision.DoesNotExist) as exc:
            raise Http404 from exc
        except PageVersionConflict:
            return Response({"code": "VERSION_CONFLICT"}, status=status.HTTP_409_CONFLICT)
        except DjangoValidationError as exc:
            return Response({"code": "INVALID_REVISION", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        page.refresh_from_db()
        return Response(WebsitePageSerializer(page, context={"request": request}).data)


class PublicWebsitePageAPIView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, hostname, slug):
        token = request.query_params.get("preview_token")
        if token:
            try:
                payload = read_preview_token(token)
                page = WebsitePage.objects.select_related("website").prefetch_related("sections").get(
                    pk=payload["page_id"], website_id=payload["website_id"], slug=slug,
                    website__domains__hostname=normalize_hostname(hostname),
                    website__domains__status=WebsiteDomain.Status.ACTIVE,
                    website__domains__verified_at__isnull=False,
                )
                if page.draft_version != payload["draft_version"]:
                    raise Http404
                return Response(build_page_snapshot(page))
            except (signing.BadSignature, signing.SignatureExpired, WebsitePage.DoesNotExist, KeyError):
                raise Http404
        try:
            _, _, revision = get_published_page_by_hostname(hostname, slug)
        except (Website.DoesNotExist, WebsitePage.DoesNotExist):
            raise Http404
        return Response(revision.snapshot)


class CurrentWebsiteDomainPrimaryAPIView(WebsitePermissionMixin, BaseCompanyAPIView, generics.GenericAPIView):
    required_company_permissions = {"PATCH": "manage.website.domains"}

    @transaction.atomic
    def patch(self, request, pk):
        try:
            domain = WebsiteDomain.objects.select_for_update().get(pk=pk, website=self.get_website())
        except WebsiteDomain.DoesNotExist as exc:
            raise Http404 from exc
        if domain.status != WebsiteDomain.Status.ACTIVE or not domain.verified_at:
            return Response({"code": "DOMAIN_NOT_ACTIVE", "detail": "El dominio debe estar activo y verificado."}, status=status.HTTP_409_CONFLICT)
        WebsiteDomain.objects.filter(website=domain.website, is_primary=True).exclude(pk=domain.pk).update(is_primary=False)
        domain.is_primary = True
        domain.save(update_fields=("is_primary", "updated_at"))
        return Response(WebsiteDomainSerializer(domain).data)


class CurrentWebsiteMediaListCreateAPIView(WebsitePermissionMixin, BaseCompanyAPIView, generics.GenericAPIView):
    parser_classes = (MultiPartParser, FormParser)
    required_company_permissions = {"GET": "read.website", "POST": "manage.website.media"}

    def get_serializer_class(self):
        return WebsiteMediaUploadSerializer if self.request.method == "POST" else WebsiteMediaSerializer

    def get(self, request):
        media = WebsiteMedia.objects.filter(website=self.get_website(), is_deleted=False)
        return Response(WebsiteMediaSerializer(media, many=True).data)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            media, created = create_website_media(
                website=self.get_website(), uploaded_file=serializer.validated_data["file"],
                kind=serializer.validated_data["kind"], alt_text=serializer.validated_data["alt_text"],
                actor=request.user,
            )
        except ProductImageStorageError as exc:
            raise DRFValidationError({"file": str(exc)}) from exc
        return Response(WebsiteMediaSerializer(media).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class CurrentWebsiteMediaDetailAPIView(WebsitePermissionMixin, BaseCompanyAPIView, generics.GenericAPIView):
    required_company_permissions = {"PATCH": "manage.website.media", "DELETE": "manage.website.media"}

    def get_object(self):
        try:
            return WebsiteMedia.objects.get(pk=self.kwargs["pk"], website=self.get_website(), is_deleted=False)
        except WebsiteMedia.DoesNotExist as exc:
            raise Http404 from exc

    def patch(self, request, pk):
        media = self.get_object()
        if "alt_text" in request.data:
            media.alt_text = str(request.data["alt_text"])[:180]
        if "kind" in request.data and request.data["kind"] in WebsiteMedia.Kind.values:
            media.kind = request.data["kind"]
        media.save(update_fields=("alt_text", "kind", "updated_at"))
        return Response(WebsiteMediaSerializer(media).data)

    def delete(self, request, pk):
        media = self.get_object()
        if media.logo_for_settings.exists() or media.favicon_for_settings.exists():
            return Response({"code": "MEDIA_IN_USE", "detail": "El medio está asignado al tema del sitio."}, status=status.HTTP_409_CONFLICT)
        media.is_deleted = True
        media.save(update_fields=("is_deleted", "updated_at"))
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentWebsiteMenuListCreateAPIView(WebsitePermissionMixin, BaseCompanyAPIView, generics.ListCreateAPIView):
    serializer_class = WebsiteMenuSerializer
    required_company_permissions = {"GET": "read.website", "POST": "manage.website"}

    def get_queryset(self):
        return WebsiteMenu.objects.filter(website=self.get_website()).prefetch_related("items__page", "items__parent")

    def perform_create(self, serializer):
        serializer.save(website=self.get_website())


class CurrentWebsiteMenuDetailAPIView(WebsitePermissionMixin, BaseCompanyAPIView, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = WebsiteMenuSerializer
    http_method_names = ("get", "patch", "delete", "head", "options")
    required_company_permissions = {"GET": "read.website", "PATCH": "manage.website", "DELETE": "manage.website"}

    def get_queryset(self):
        return WebsiteMenu.objects.filter(website=self.get_website()).prefetch_related("items__page", "items__parent")


class CurrentWebsiteMenuItemsAPIView(WebsitePermissionMixin, BaseCompanyAPIView, generics.GenericAPIView):
    serializer_class = ReplaceMenuItemsSerializer
    required_company_permissions = {"PUT": "manage.website"}

    def put(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            menu = WebsiteMenu.objects.get(pk=pk, website=self.get_website())
            menu = replace_menu_items(menu=menu, **serializer.validated_data)
        except WebsiteMenu.DoesNotExist as exc:
            raise Http404 from exc
        except MenuVersionConflict:
            return Response({"code": "VERSION_CONFLICT", "detail": "El menú cambió desde que se abrió."}, status=status.HTTP_409_CONFLICT)
        except DjangoValidationError as exc:
            raise DRFValidationError({"items": str(exc)}) from exc
        return Response(WebsiteMenuSerializer(menu, context={"request": request}).data)


class CurrentWebsiteMenuPublishAPIView(WebsitePermissionMixin, BaseCompanyAPIView, generics.GenericAPIView):
    serializer_class = PublishMenuSerializer
    required_company_permissions = {"POST": "publish.website"}

    def post(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            menu = WebsiteMenu.objects.get(pk=pk, website=self.get_website())
            menu = publish_menu(menu=menu, **serializer.validated_data)
        except WebsiteMenu.DoesNotExist as exc:
            raise Http404 from exc
        except MenuVersionConflict:
            return Response({"code": "VERSION_CONFLICT", "detail": "El menú cambió desde que se abrió."}, status=status.HTTP_409_CONFLICT)
        return Response(WebsiteMenuSerializer(menu, context={"request": request}).data)


class PublicWebsiteManifestAPIView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, hostname):
        try:
            website = get_public_website_by_hostname(hostname)
        except (Website.DoesNotExist, DjangoValidationError):
            raise Http404
        primary = website.domains.filter(status=WebsiteDomain.Status.ACTIVE, is_primary=True).first()
        domain = primary or website.domains.filter(hostname=normalize_hostname(hostname)).first()
        pages = WebsitePage.objects.filter(
            website=website, status=WebsitePage.Status.PUBLISHED, published_version__gt=0,
        ).order_by("slug")
        products = WebsiteProduct.objects.filter(
            website=website, is_published=True, product__active=True,
        ).order_by("slug")
        return Response({
            "canonical_url": f"https://{domain.hostname}",
            "default_noindex": website.settings.default_noindex,
            "pages": [
                {"slug": page.slug, "updated_at": page.published_at, "noindex": page.noindex}
                for page in pages
            ],
            "products": [
                {"slug": product.slug, "updated_at": product.updated_at}
                for product in products
            ],
        })
