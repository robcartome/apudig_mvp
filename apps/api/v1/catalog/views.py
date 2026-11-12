import logging
import uuid
from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, DecimalField, OuterRef, Prefetch, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.http import Http404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, permissions
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.base import BaseCompanyAPIView
from apps.api.v1.catalog.pagination import CatalogLegacyPagination
from apps.api.v1.catalog.serializers import (
    CatalogProductDetailSerializer,
    CatalogProductListSerializer,
    StorefrontProductDetailSerializer,
    StorefrontProductListSerializer,
    PublishedWebsiteProductSerializer,
    StorefrontTaxonomySerializer,
    StorefrontResolveSerializer,
    StorefrontCartQuoteRequestSerializer,
    StorefrontCartQuoteSerializer,
)
from apps.api.v1.catalog.throttles import StorefrontQuoteThrottle
from apps.api.v1.permissions import HasCompanyPermission
from apps.inventory import selectors as inventory_selectors
from apps.inventory.models import Brand, Category, ProductSupplier, StockByWarehouse
from apps.websites.models import Website, normalize_hostname
from apps.websites.selectors import (
    get_catalog_settings,
    get_public_website_by_hostname,
    get_public_website_products,
)


logger = logging.getLogger(__name__)


def _optional_uuid(value, field_name):
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({field_name: "Use un identificador válido."}) from exc


def _active_supplier_codes_prefetch():
    return Prefetch(
        "supplier_relations",
        queryset=(
            ProductSupplier.objects.filter(active=True)
            .exclude(supplier_code="")
            .only("product_id", "supplier_code")
            .order_by("supplier_code")
        ),
        to_attr="active_supplier_code_relations",
    )


class StorefrontWebsiteMixin:
    """Resolve a required registered hostname and expose its company scope."""

    authentication_classes = []
    website = None
    storefront_request_id = None

    def get_storefront_request_id(self):
        if self.storefront_request_id:
            return self.storefront_request_id
        candidate = self.request.headers.get("X-Request-ID", "")
        try:
            self.storefront_request_id = str(uuid.UUID(candidate))
        except (TypeError, ValueError, AttributeError):
            self.storefront_request_id = str(uuid.uuid4())
        return self.storefront_request_id

    def get_hostname(self):
        return self.kwargs.get("hostname")

    def get_website(self):
        if self.website is not None:
            return self.website
        hostname = (self.get_hostname() or "").strip()
        if not hostname:
            raise ValidationError({"site": "El dominio de la tienda es obligatorio."})
        try:
            self.website = get_public_website_by_hostname(hostname)
        except (Website.DoesNotExist, DjangoValidationError) as exc:
            raise Http404("La tienda solicitada no existe o no está publicada.") from exc
        logger.info(
            "storefront.website_resolved request_id=%s website_id=%s hostname=%s",
            self.get_storefront_request_id(),
            self.website.pk,
            normalize_hostname(hostname),
        )
        return self.website

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["X-Request-ID"] = self.get_storefront_request_id()
        return response


class StorefrontResolveAPIView(StorefrontWebsiteMixin, APIView):
    permission_classes = [permissions.AllowAny]

    def get_hostname(self):
        return self.request.query_params.get("hostname")

    @extend_schema(
        tags=["Storefront"],
        summary="Resolve a published storefront hostname",
        parameters=[
            OpenApiParameter(
                name="hostname",
                required=True,
                type=str,
                description="Registered hostname without protocol, port or path.",
            ),
        ],
        responses={200: StorefrontResolveSerializer},
    )
    def get(self, request):
        website = self.get_website()
        domain = website.domains.get(hostname=normalize_hostname(self.get_hostname()))
        primary_domain = next(
            (
                item
                for item in website.domains.all()
                if item.status == item.Status.ACTIVE and item.is_primary
            ),
            domain,
        )
        site_settings = website.settings
        catalog_settings = get_catalog_settings(website)
        published_menus = {
            menu.location.lower(): menu.published_items
            for menu in website.menus.filter(status="PUBLISHED", enabled=True)
        }
        logo_url = (
            site_settings.logo_media.url
            if site_settings.logo_media and not site_settings.logo_media.is_deleted
            else site_settings.logo_url
        )
        favicon_url = (
            site_settings.favicon_media.url
            if site_settings.favicon_media and not site_settings.favicon_media.is_deleted
            else site_settings.favicon_url
        )
        return Response({
            "website_id": str(website.pk),
            "template_key": website.template_key,
            "template_schema_version": website.template_schema_version,
            "hostname": domain.hostname,
            "canonical_url": f"https://{primary_domain.hostname}",
            "canonical_hostname": primary_domain.hostname,
            "is_primary": domain.pk == primary_domain.pk,
            "name": site_settings.business_name or website.name,
            "locale": website.default_locale,
            "currency": website.currency,
            "theme": {
                "primary_color": site_settings.primary_color,
                "accent_color": site_settings.accent_color,
                "background_color": site_settings.background_color,
                "text_color": site_settings.text_color,
                "logo": {
                    "url": logo_url,
                    "alt": site_settings.business_name or website.name,
                },
                "favicon_url": favicon_url,
                "heading_font": site_settings.heading_font,
                "body_font": site_settings.body_font,
                "border_radius": site_settings.border_radius,
            },
            "contact": {
                "whatsapp": site_settings.whatsapp,
                "phone": site_settings.phone,
                "email": site_settings.email,
                "address": site_settings.address,
                "business_hours": site_settings.business_hours,
                "social_links": site_settings.social_links,
                "google_maps_url": site_settings.google_maps_url,
            },
            "seo": {
                "title": site_settings.default_seo_title or site_settings.business_name or website.name,
                "description": site_settings.default_seo_description,
                "noindex": site_settings.default_noindex,
            },
            "menus": published_menus,
            "footer_text": site_settings.footer_text,
            "publication_version": max(
                website.pages.values_list("published_version", flat=True), default=0
            ),
            "catalog": {
                "products_per_page": catalog_settings.products_per_page,
            },
        })


class StorefrontProductListAPIView(StorefrontWebsiteMixin, generics.ListAPIView):
    serializer_class = PublishedWebsiteProductSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = CatalogLegacyPagination

    def get_queryset(self):
        website = self.get_website()
        search = (self.request.query_params.get("search") or "").strip()
        brand = (self.request.query_params.get("brand") or "").strip()
        category = (self.request.query_params.get("category") or "").strip()

        qs = get_public_website_products(website)
        if search:
            qs = qs.filter(
                Q(commercial_title__icontains=search)
                | Q(product__name__icontains=search)
                | Q(product__sku__icontains=search)
            )
        brand_id = _optional_uuid(brand, "brand")
        category_id = _optional_uuid(category, "category")
        if brand_id:
            qs = qs.filter(product__brand_id=brand_id)
        if category_id:
            qs = qs.filter(product__category_id=category_id)
        ordering = (self.request.query_params.get("ordering") or "").strip()
        order_map = {
            "name": ("commercial_title", "product__name"),
            "-name": ("-commercial_title", "-product__name"),
            "price": ("public_price", "product__name"),
            "-price": ("-public_price", "product__name"),
        }
        return qs.order_by(*order_map.get(ordering, ("position", "product__name")))

    def get_serializer_context(self):
        context = super().get_serializer_context()
        website = self.get_website()
        context.update({
            "website": website,
            "catalog_settings": get_catalog_settings(website),
        })
        return context

    @extend_schema(
        tags=["Storefront"],
        summary="List public products for a registered storefront",
        parameters=[
            OpenApiParameter(name="hostname", location=OpenApiParameter.PATH, required=True, type=str),
            OpenApiParameter(name="search", required=False, type=str),
            OpenApiParameter(name="brand", required=False, type=str),
            OpenApiParameter(name="category", required=False, type=str),
            OpenApiParameter(name="limit", required=False, type=int),
            OpenApiParameter(name="offset", required=False, type=int),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class StorefrontProductDetailAPIView(StorefrontWebsiteMixin, generics.RetrieveAPIView):
    serializer_class = PublishedWebsiteProductSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        website = self.get_website()
        return get_public_website_products(website)

    def get_object(self):
        identifier = self.kwargs.get("identifier", "")
        queryset = self.get_queryset()
        try:
            product_id = uuid.UUID(identifier)
        except (ValueError, TypeError):
            product_id = None
        filters = Q(slug=identifier)
        if product_id:
            filters |= Q(product_id=product_id)
        try:
            return queryset.get(filters)
        except queryset.model.DoesNotExist as exc:
            raise Http404("El producto no está publicado en este sitio.") from exc

    def get_serializer_context(self):
        context = super().get_serializer_context()
        website = self.get_website()
        context.update({
            "website": website,
            "catalog_settings": get_catalog_settings(website),
        })
        return context

    @extend_schema(
        tags=["Storefront"],
        summary="Retrieve a public product from a registered storefront",
        parameters=[
            OpenApiParameter(name="hostname", location=OpenApiParameter.PATH, required=True, type=str),
        ],
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


class LegacyStorefrontMixin(StorefrontWebsiteMixin):
    """Temporary compatibility contract for /catalog/* consumers."""

    def get_hostname(self):
        return self.request.query_params.get("site")


class CatalogProductListAPIView(LegacyStorefrontMixin, StorefrontProductListAPIView):
    serializer_class = StorefrontProductListSerializer

    def get_queryset(self):
        website = self.get_website()
        search = (self.request.query_params.get("search") or "").strip()
        brand = (self.request.query_params.get("brand") or "").strip()
        category = (self.request.query_params.get("category") or "").strip()
        queryset = inventory_selectors.get_products(
            company_id=website.company_id, active_only=True
        )
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(sku__icontains=search))
        brand_id = _optional_uuid(brand, "brand")
        category_id = _optional_uuid(category, "category")
        if brand_id:
            queryset = queryset.filter(brand_id=brand_id)
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        return queryset

    def get_serializer_context(self):
        return generics.ListAPIView.get_serializer_context(self)

    @extend_schema(
        tags=["Catalog"],
        summary="Deprecated public catalog; requires a registered site",
        deprecated=True,
        parameters=[
            OpenApiParameter(name="site", required=True, type=str),
            OpenApiParameter(name="search", required=False, type=str),
            OpenApiParameter(name="brand", required=False, type=str),
            OpenApiParameter(name="category", required=False, type=str),
            OpenApiParameter(name="limit", required=False, type=int),
            OpenApiParameter(name="offset", required=False, type=int),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class CatalogProductDetailAPIView(LegacyStorefrontMixin, StorefrontProductDetailAPIView):
    serializer_class = StorefrontProductDetailSerializer

    def get_queryset(self):
        website = self.get_website()
        return inventory_selectors.get_products(
            company_id=website.company_id, active_only=True
        )

    def get_object(self):
        return generics.RetrieveAPIView.get_object(self)

    def get_serializer_context(self):
        return generics.RetrieveAPIView.get_serializer_context(self)

    @extend_schema(
        tags=["Catalog"],
        summary="Deprecated public product detail; requires a registered site",
        deprecated=True,
        parameters=[OpenApiParameter(name="site", required=True, type=str)],
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


class StorefrontCategoryListAPIView(StorefrontWebsiteMixin, generics.ListAPIView):
    serializer_class = StorefrontTaxonomySerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    def get_queryset(self):
        website = self.get_website()
        return (
            Category.objects.filter(
                company_id=website.company_id,
                active=True,
                products__active=True,
                products__website_publications__website=website,
                products__website_publications__is_published=True,
            )
            .annotate(product_count=Count("products__website_publications", distinct=True))
            .order_by("name")
            .distinct()
        )


class StorefrontBrandListAPIView(StorefrontWebsiteMixin, generics.ListAPIView):
    serializer_class = StorefrontTaxonomySerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    def get_queryset(self):
        website = self.get_website()
        return (
            Brand.objects.filter(
                company_id=website.company_id,
                active=True,
                products__active=True,
                products__website_publications__website=website,
                products__website_publications__is_published=True,
            )
            .annotate(product_count=Count("products__website_publications", distinct=True))
            .order_by("name")
            .distinct()
        )


class StorefrontCartQuoteAPIView(StorefrontWebsiteMixin, APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [StorefrontQuoteThrottle]

    @extend_schema(
        tags=["Storefront"],
        summary="Revalidate a public cart and create a signed quotation snapshot",
        request=StorefrontCartQuoteRequestSerializer,
        responses={200: StorefrontCartQuoteSerializer},
    )
    def post(self, request, hostname):
        input_serializer = StorefrontCartQuoteRequestSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        website = self.get_website()
        catalog_settings = get_catalog_settings(website)
        requested_lines = input_serializer.validated_data["lines"]
        requested_ids = [line["product_id"] for line in requested_lines]
        publications = {
            publication.product_id: publication
            for publication in get_public_website_products(
                website, include_hidden_out_of_stock=True
            ).filter(product_id__in=requested_ids)
        }

        lines = []
        total = Decimal("0.00")
        has_changes = False
        for requested in requested_lines:
            product_id = requested["product_id"]
            quantity = requested["quantity"]
            publication = publications.get(product_id)
            if publication is None:
                has_changes = True
                lines.append({
                    "product_id": product_id,
                    "quantity": quantity,
                    "status": "REMOVED",
                })
                continue

            public_data = PublishedWebsiteProductSerializer(
                publication,
                context={
                    "website": website,
                    "catalog_settings": catalog_settings,
                },
            ).data
            price = Decimal(public_data["price"])
            status_value = (
                "OUT_OF_STOCK"
                if public_data["availability"] == "OUT_OF_STOCK"
                else "ACTIVE"
            )
            subtotal = (price * quantity).quantize(Decimal("0.01"))
            if status_value == "ACTIVE":
                total += subtotal
            else:
                has_changes = True
            lines.append({
                "product_id": product_id,
                "status": status_value,
                "quantity": quantity,
                "slug": public_data["slug"],
                "sku": public_data["sku"],
                "name": public_data["name"],
                "unit": public_data["unit"],
                "price": price,
                "subtotal": subtotal,
                "availability": public_data["availability"],
                "image": public_data["thumbnail"] or public_data["image"],
            })

        now = timezone.now()
        expires_at = now + timedelta(
            seconds=getattr(settings, "STOREFRONT_QUOTE_TTL", 900)
        )
        quote_id = uuid.uuid4()
        token_payload = {
            "v": 1,
            "quote_id": str(quote_id),
            "website_id": str(website.pk),
            "currency": website.currency,
            "total": str(total),
            "lines": [
                {
                    "product_id": str(line["product_id"]),
                    "quantity": line["quantity"],
                    "price": str(line.get("price", "")),
                    "status": line["status"],
                }
                for line in lines
            ],
        }
        quote_token = signing.dumps(
            token_payload, salt="storefront-cart-quote-v1", compress=True
        )
        payload = {
            "version": 1,
            "quote_id": quote_id,
            "quote_token": quote_token,
            "quoted_at": now,
            "expires_at": expires_at,
            "currency": website.currency,
            "total": total,
            "has_changes": has_changes,
            "can_submit": all(line["status"] == "ACTIVE" for line in lines),
            "lines": lines,
        }
        return Response(StorefrontCartQuoteSerializer(payload).data)


class PrivateCatalogProductListAPIView(BaseCompanyAPIView, generics.ListAPIView):
    serializer_class = CatalogProductListSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_company_permission = "read.inventory.products"
    pagination_class = CatalogLegacyPagination
    company_required = True

    def get_queryset(self):
        company_id = self.get_required_company_id()
        search = (self.request.query_params.get("search") or "").strip()
        brand = (self.request.query_params.get("brand") or "").strip()
        category = (self.request.query_params.get("category") or "").strip()

        qs = inventory_selectors.search_products(
            search,
            company_id=company_id,
            active_only=True,
        ).prefetch_related(_active_supplier_codes_prefetch())
        if brand:
            qs = qs.filter(brand_id=brand)
        if category:
            qs = qs.filter(category_id=category)

        stock_subquery = Subquery(
            StockByWarehouse.objects
            .filter(product=OuterRef("pk"))
            .values("product")
            .annotate(total=Sum("quantity"))
            .values("total")[:1],
            output_field=DecimalField(max_digits=14, decimal_places=3),
        )
        return qs.annotate(
            stock=Coalesce(
                stock_subquery,
                Decimal("0"),
                output_field=DecimalField(max_digits=14, decimal_places=3),
            )
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["include_purchase_price"] = True
        return context


class PrivateCatalogProductDetailAPIView(BaseCompanyAPIView, generics.RetrieveAPIView):
    serializer_class = CatalogProductDetailSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_company_permission = "read.inventory.products"
    company_required = True

    def get_queryset(self):
        company_id = self.get_required_company_id()
        return inventory_selectors.get_products(
            company_id=company_id,
            active_only=True,
        ).prefetch_related(
            "prices__price_list",
            "stocks__warehouse",
            _active_supplier_codes_prefetch(),
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["include_purchase_price"] = True
        return context
