from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.cache import patch_vary_headers
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions
from rest_framework.response import Response

from apps.api.v1.websites.views import WebsiteAPIView, WebsiteReadOnlyAPIView
from apps.api.v1.catalog.access import CatalogJWTAuthentication
from apps.inventory.models import Product
from apps.websites.catalog import selectors, services
from apps.websites.catalog.projection import product_data
from apps.websites.errors import WebsiteError
from apps.websites.models import WebsiteCatalogSettings, WebsiteProduct
from .serializers import (
    CatalogErrorSerializer, CatalogSettingsPatchSerializer, CatalogSettingsSerializer, PageQuerySerializer,
    ProductOptionsPageSerializer, ProductQuerySerializer, PublicationCreateSerializer,
    PublicationPatchSerializer, PublicationSerializer, PublicationsPageSerializer,
    PublicBrandsPageSerializer, PublicCategoriesPageSerializer, PublicProductResponseSerializer,
    PublicProductsPageSerializer, SearchPageQuerySerializer,
)


def catalog_schema(**kwargs):
    response = kwargs.pop("responses")
    responses = response if isinstance(response, dict) else {200: response}
    errors = {400: CatalogErrorSerializer, 404: CatalogErrorSerializer, 503: CatalogErrorSerializer}
    if kwargs.get("auth") != []:
        errors.update({401: CatalogErrorSerializer, 403: CatalogErrorSerializer})
    if "request" in kwargs:
        errors.update({409: CatalogErrorSerializer, 412: CatalogErrorSerializer, 428: CatalogErrorSerializer})
    return extend_schema(responses={**errors, **responses}, **kwargs)


COMMERCIAL_ETAG = OpenApiParameter(name="ETag", type=str, location=OpenApiParameter.HEADER, response=[200, 201, 204], description='Opaque commercial aggregate ETag, independent from editorial revision.')
COMMERCIAL_IF_MATCH = OpenApiParameter(name="If-Match", type=str, location=OpenApiParameter.HEADER, required=True, description='Strong commercial ETag from K5/K6. Missing: 428; obsolete: 412. Editorial ETags are invalid.')
PAGE_PARAMS = [OpenApiParameter(name="limit", type={"type": "integer", "minimum": 1, "maximum": 100}), OpenApiParameter(name="offset", type={"type": "integer", "minimum": 0, "maximum": 2**31 - 1})]
SEARCH_PARAMS = [OpenApiParameter(name="search", type=str), *PAGE_PARAMS]
PRODUCT_PARAMS = [*SEARCH_PARAMS,
    OpenApiParameter(name="category", type=str, many=True), OpenApiParameter(name="brand", type=str, many=True),
    OpenApiParameter(name="min", type=str), OpenApiParameter(name="max", type=str),
    OpenApiParameter(name="featured", type=bool),
    OpenApiParameter(name="ordering", type=str, enum=["name", "name-desc", "price-asc", "price-desc", "featured"]),
]


def query_values(request, serializer_class, *, default_limit=24):
    values = {}
    for key in request.query_params:
        entries = request.query_params.getlist(key)
        if key in ("category", "brand"):
            values[key] = entries
        elif len(entries) != 1:
            raise WebsiteError("No repitas este parámetro.", fields={key: "Parámetro duplicado."})
        else:
            values[key] = entries[0]
    serializer = serializer_class(data=values)
    serializer.is_valid(raise_exception=True)
    result = dict(serializer.validated_data)
    result.setdefault("limit", default_limit)
    return result


def page_data(queryset, website, query, project):
    limit, offset = query["limit"], query["offset"]
    return {"websiteId": str(website.pk), "count": queryset.count(), "limit": limit, "offset": offset, "results": [project(row) for row in queryset[offset:offset + limit]]}


class PublicCatalogAPIView(WebsiteReadOnlyAPIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]


class PublicProductListAPIView(PublicCatalogAPIView):
    @catalog_schema(operation_id="website_catalog_products_list", tags=["Website catalog"], auth=[], parameters=PRODUCT_PARAMS, responses=PublicProductsPageSerializer)
    def get(self, request, hostname):
        website = selectors.public_website(hostname)
        configuration = WebsiteCatalogSettings.objects.defer("commerce_enabled").filter(website=website).first()
        query = query_values(request, ProductQuerySerializer, default_limit=configuration.products_per_page if configuration else 24)
        offers = selectors.catalog_offers(website, configuration=configuration)
        results = selectors.order_offers(selectors.filter_offers(offers, query), query["ordering"])
        data = page_data(results, website, query, lambda row: product_data(row, website))
        data["facets"] = {
            "categories": selectors.facet_rows(selectors.filter_offers(offers, query, exclude_group="category"), website, "category"),
            "brands": selectors.facet_rows(selectors.filter_offers(offers, query, exclude_group="brand"), website, "brand"),
        }
        return Response(PublicProductsPageSerializer(data).data)


class PublicProductDetailAPIView(PublicCatalogAPIView):
    @catalog_schema(operation_id="website_catalog_products_detail", tags=["Website catalog"], auth=[], responses=PublicProductResponseSerializer)
    def get(self, request, hostname, product_id):
        website = selectors.public_website(hostname)
        if request.query_params:
            raise WebsiteError("Este detalle no admite parámetros de contexto.")
        publication = get_object_or_404(selectors.catalog_offers(website, detail=True), product_id=product_id)
        return Response(PublicProductResponseSerializer({"websiteId": str(website.pk), "product": product_data(publication, website, detail=True)}).data)


class PublicCategoryListAPIView(PublicCatalogAPIView):
    group = "category"
    serializer_class = PublicCategoriesPageSerializer

    @catalog_schema(tags=["Website catalog"], auth=[], parameters=PAGE_PARAMS, responses=PublicCategoriesPageSerializer)
    def get(self, request, hostname):
        website = selectors.public_website(hostname)
        query = query_values(request, PageQuerySerializer, default_limit=100)
        rows = selectors.facet_rows(selectors.catalog_offers(website), website, self.group)
        limit, offset = query["limit"], query["offset"]
        return Response(self.serializer_class({"websiteId": str(website.pk), "count": len(rows), "limit": limit, "offset": offset, "results": rows[offset:offset + limit]}).data)


class PublicBrandListAPIView(PublicCategoryListAPIView):
    group = "brand"
    serializer_class = PublicBrandsPageSerializer

    @catalog_schema(tags=["Website catalog"], auth=[], parameters=PAGE_PARAMS, responses=PublicBrandsPageSerializer)
    def get(self, request, hostname):
        return super().get(request, hostname)


class CommercialAPIView(WebsiteAPIView):
    authentication_classes = [CatalogJWTAuthentication]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        patch_vary_headers(response, ("Authorization",))
        return response


class CatalogProductOptionsAPIView(CommercialAPIView):
    http_method_names = ["get", "head", "options"]
    @catalog_schema(tags=["Website catalog admin"], parameters=SEARCH_PARAMS, responses=ProductOptionsPageSerializer)
    def get(self, request, website_id):
        website, _ = services.authorized_website(**self.context(), website_id=website_id, operation="edit")
        query = query_values(request, SearchPageQuerySerializer)
        products = Product.objects.filter(company_id=website.company_id, active=True).select_related("unit").order_by("name", "pk")
        if query["search"]:
            products = products.filter(Q(name__icontains=query["search"]) | Q(sku__icontains=query["search"]))
        data = page_data(products, website, query, lambda row: {"productId": str(row.pk), "name": row.name, "sku": row.sku, "unitId": str(row.unit_id), "unit": row.unit.name})
        return Response(ProductOptionsPageSerializer(data).data)


class CatalogSettingsAPIView(CommercialAPIView):
    http_method_names = ["get", "patch", "head", "options"]

    @catalog_schema(tags=["Website catalog admin"], parameters=[COMMERCIAL_ETAG], responses=CatalogSettingsSerializer)
    def get(self, request, website_id):
        if request.query_params:
            raise WebsiteError("La configuración no admite parámetros de contexto.")
        data, etag = services.read_configuration(**self.context(), website_id=website_id)
        return Response(CatalogSettingsSerializer(data).data, headers={"ETag": etag})

    @catalog_schema(tags=["Website catalog admin"], parameters=[COMMERCIAL_IF_MATCH, COMMERCIAL_ETAG], request=CatalogSettingsPatchSerializer, responses=CatalogSettingsSerializer)
    def patch(self, request, website_id):
        serializer = CatalogSettingsPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data, etag = services.update_configuration(**self.context(), website_id=website_id, data=serializer.validated_data, expected=request.headers.get("If-Match"))
        return Response(CatalogSettingsSerializer(data).data, headers={"ETag": etag})


class WebsitePublicationListAPIView(CommercialAPIView):
    http_method_names = ["get", "post", "head", "options"]

    @catalog_schema(tags=["Website catalog admin"], parameters=[*SEARCH_PARAMS, COMMERCIAL_ETAG], responses=PublicationsPageSerializer)
    @transaction.atomic
    def get(self, request, website_id):
        website, capabilities = services.authorized_website(**self.context(), website_id=website_id, lock=True)
        query = query_values(request, SearchPageQuerySerializer)
        publications = WebsiteProduct.objects.filter(website=website, product__company_id=website.company_id).order_by("position", "pk")
        if query["search"]:
            publications = publications.filter(Q(product__name__icontains=query["search"]) | Q(product__sku__icontains=query["search"]) | Q(commercial_title__icontains=query["search"]))
        data = page_data(publications, website, query, lambda row: services.publication_data(row, capabilities))
        return Response(PublicationsPageSerializer(data).data, headers={"ETag": services.commercial_etag(website)})

    @catalog_schema(tags=["Website catalog admin"], parameters=[COMMERCIAL_IF_MATCH, COMMERCIAL_ETAG], request=PublicationCreateSerializer, responses={201: PublicationSerializer})
    def post(self, request, website_id):
        serializer = PublicationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data, etag = services.write_publication(**self.context(), website_id=website_id, data=serializer.validated_data, expected=request.headers.get("If-Match"))
        return Response(PublicationSerializer(data).data, status=201, headers={"ETag": etag})


class WebsitePublicationDetailAPIView(CommercialAPIView):
    http_method_names = ["patch", "delete", "options"]

    @catalog_schema(tags=["Website catalog admin"], parameters=[COMMERCIAL_IF_MATCH, COMMERCIAL_ETAG], request=PublicationPatchSerializer, responses=PublicationSerializer)
    def patch(self, request, website_id, publication_id):
        serializer = PublicationPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data, etag = services.write_publication(**self.context(), website_id=website_id, publication_id=publication_id, data=serializer.validated_data, expected=request.headers.get("If-Match"))
        return Response(PublicationSerializer(data).data, headers={"ETag": etag})

    @catalog_schema(tags=["Website catalog admin"], parameters=[COMMERCIAL_IF_MATCH, COMMERCIAL_ETAG], request=None, responses={204: None})
    def delete(self, request, website_id, publication_id):
        if request.data not in ({}, None):
            raise WebsiteError("Eliminar el vínculo no admite contenido adicional.")
        _, etag = services.write_publication(**self.context(), website_id=website_id, publication_id=publication_id, data={}, delete=True, expected=request.headers.get("If-Match"))
        return Response(status=204, headers={"ETag": etag})
