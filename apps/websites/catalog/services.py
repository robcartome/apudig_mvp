"""Commercial aggregate writes lock Website; editorial ETags remain untouched."""
import hashlib
import json
import re

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.models import AuditLog
from apps.inventory.models import PriceList, Product, Warehouse
from apps.websites.errors import WebsiteError
from apps.websites.models import Website, WebsiteCatalogSettings, WebsiteProduct
from apps.websites.selectors import get_company_website
from .permissions import require_catalog_permission


def authorized_website(*, user, company_id, website_id, store_id=None, operation="read", lock=False):
    context = {"user": user, "company_id": company_id, "store_id": store_id}
    capabilities = require_catalog_permission(operation=operation, **context)
    website = get_company_website(**context, website_id=website_id)
    if lock:
        website = Website.objects.select_for_update().get(pk=website.pk, company_id=website.company_id)
        capabilities = require_catalog_permission(operation=operation, **context)
    return website, capabilities


def commercial_etag(website):
    settings = WebsiteCatalogSettings.objects.filter(website=website).first()
    state = {
        "website": str(website.pk), "currency": website.currency,
        "settings": None if settings is None else [
            str(settings.pk), str(settings.default_price_list_id), settings.show_out_of_stock,
            settings.products_per_page, settings.updated_at.isoformat(),
            list(map(str, settings.warehouses.order_by("pk").values_list("pk", flat=True))),
        ],
        "products": list(WebsiteProduct.objects.filter(website=website).order_by("pk").values(
            "id", "product_id", "price_list_id", "slug", "commercial_title", "commercial_description",
            "seo_title", "seo_description", "is_published", "is_featured", "position", "updated_at",
        )),
    }
    digest = hashlib.sha256(json.dumps(state, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    return f'"catalog-{digest}"'


def check_precondition(website, expected):
    if expected is None:
        raise WebsiteError("If-Match es obligatorio.", code="PRECONDITION_REQUIRED", status=428)
    if not re.fullmatch(r'"catalog-[0-9a-f]{64}"', expected):
        raise WebsiteError("Usa el ETag comercial recibido, sin modificarlo.")
    if commercial_etag(website) != expected:
        raise WebsiteError("El catálogo cambió. Recarga antes de continuar.", code="CATALOG_CONFLICT", status=412)


def audit_change(user, website, action, before, after):
    changes = json.loads(json.dumps({"before": before, "after": after}, default=str))
    AuditLog.objects.create(user=user, action=action, entity="WebsiteCatalog", entity_id=str(website.pk), meta_data=changes)


def configuration_data(website, capabilities):
    configuration = WebsiteCatalogSettings.objects.filter(website=website).first()
    data = {
        "websiteId": str(website.pk), "currency": website.currency, "commerceEnabled": False,
        "showOutOfStock": configuration.show_out_of_stock if configuration else True,
        "productsPerPage": configuration.products_per_page if configuration else 24,
        "canManagePolicy": capabilities["policy"],
    }
    if capabilities["policy"]:
        data.update(
            defaultPriceListId=str(configuration.default_price_list_id) if configuration and configuration.default_price_list_id else None,
            warehouseIds=list(map(str, configuration.warehouses.order_by("pk").values_list("pk", flat=True))) if configuration else [],
            priceListOptions=[{"id": str(row.pk), "name": row.name, "pricesIncludeTax": row.prices_include_tax} for row in PriceList.objects.filter(company_id=website.company_id, active=True).order_by("name", "pk")],
            warehouseOptions=[{"id": str(row.pk), "name": row.name, "storeId": str(row.store_id)} for row in Warehouse.objects.filter(store__company_id=website.company_id, store__active=True, active=True).order_by("name", "pk")],
        )
    return data


def publication_data(publication, capabilities):
    data = {
        "id": str(publication.pk), "productId": str(publication.product_id), "slug": publication.slug,
        "commercialTitle": publication.commercial_title, "commercialDescription": publication.commercial_description,
        "seoTitle": publication.seo_title, "seoDescription": publication.seo_description,
        "isPublished": publication.is_published, "isFeatured": publication.is_featured,
        "position": publication.position, "updatedAt": publication.updated_at,
    }
    if capabilities["policy"]:
        data["priceListId"] = str(publication.price_list_id) if publication.price_list_id else None
    return data


def validate_price_list(website, identifier, *, field="priceListId"):
    if identifier is not None and not PriceList.objects.filter(pk=identifier, company_id=website.company_id, active=True).exists():
        raise WebsiteError("Selecciona una lista activa autorizada de esta empresa.", fields={field: "Lista no autorizada."})


@transaction.atomic
def read_configuration(**context):
    website, capabilities = authorized_website(**context, lock=True)
    return configuration_data(website, capabilities), commercial_etag(website)


@transaction.atomic
def update_configuration(*, data, expected, **context):
    website, capabilities = authorized_website(**context, operation="policy", lock=True)
    check_precondition(website, expected)
    if "defaultPriceListId" in data:
        validate_price_list(website, data["defaultPriceListId"], field="defaultPriceListId")
    if "warehouseIds" in data:
        authorized = Warehouse.objects.filter(pk__in=data["warehouseIds"], active=True, store__active=True, store__company_id=website.company_id).count()
        if authorized != len(data["warehouseIds"]):
            raise WebsiteError("Selecciona almacenes activos de esta empresa.", fields={"warehouseIds": "Selección no autorizada o duplicada."})
    configuration = WebsiteCatalogSettings.objects.filter(website=website).first()
    before = configuration_data(website, {"policy": True})
    if configuration is None:
        configuration = WebsiteCatalogSettings(website=website)
    for key, field in (("defaultPriceListId", "default_price_list_id"), ("showOutOfStock", "show_out_of_stock"), ("productsPerPage", "products_per_page")):
        if key in data:
            setattr(configuration, field, data[key])
    try:
        configuration.save()
    except ValidationError as exc:
        raise WebsiteError("Revisa la configuración comercial.", fields=getattr(exc, "message_dict", {})) from exc
    if "warehouseIds" in data:
        configuration.warehouses.set(data["warehouseIds"])
    after = configuration_data(website, capabilities)
    audit_change(context["user"], website, "WEBSITE_CATALOG_POLICY", before, after)
    return after, commercial_etag(website)


PUBLICATION_FIELDS = {
    "isPublished": "is_published", "isFeatured": "is_featured", "position": "position",
    "priceListId": "price_list_id", "commercialTitle": "commercial_title",
    "commercialDescription": "commercial_description", "seoTitle": "seo_title", "seoDescription": "seo_description",
}


@transaction.atomic
def write_publication(*, data, expected, publication_id=None, delete=False, **context):
    website, capabilities = authorized_website(**context, operation="edit", lock=True)
    check_precondition(website, expected)
    publication = None
    if publication_id:
        publication = WebsiteProduct.objects.filter(website=website, pk=publication_id, product__company_id=website.company_id).first()
        if publication is None:
            raise WebsiteProduct.DoesNotExist
    if delete or (publication and publication.is_published) or data.get("isPublished"):
        require_catalog_permission(operation="publish", **{key: context[key] for key in ("user", "company_id", "store_id") if key in context})
    if "priceListId" in data:
        require_catalog_permission(operation="policy", **{key: context[key] for key in ("user", "company_id", "store_id") if key in context})
        validate_price_list(website, data["priceListId"])
    before = publication_data(publication, {"policy": True}) if publication else None
    if publication is None:
        product = Product.objects.filter(pk=data["productId"], company_id=website.company_id, active=True).first()
        if product is None:
            raise WebsiteError("Selecciona un producto activo de esta empresa.", fields={"productId": "Producto no autorizado."})
        if WebsiteProduct.objects.filter(website=website, product=product).exists():
            raise WebsiteError("El producto ya tiene un vínculo en este Website.", code="ALREADY_EXISTS", status=409)
        publication = WebsiteProduct(website=website, product=product)
    if delete:
        publication.delete()
        after = None
    else:
        if not Product.objects.filter(pk=publication.product_id, company_id=website.company_id, active=True).exists():
            # Withdrawal must remain possible after the ERP deactivates a product.
            if data != {"isPublished": False}:
                raise WebsiteError("El producto no está activo.", fields={"productId": "Producto no autorizado."})
        for key, field in PUBLICATION_FIELDS.items():
            if key in data:
                setattr(publication, field, data[key])
        try:
            publication.save()
        except ValidationError as exc:
            raise WebsiteError("Revisa la publicación comercial.", fields=getattr(exc, "message_dict", {})) from exc
        after = publication_data(publication, {"policy": True})
    audit_change(context["user"], website, "WEBSITE_PRODUCT_DELETE" if delete else "WEBSITE_PRODUCT_WRITE", before, json.loads(json.dumps(after, default=str)))
    return publication_data(publication, capabilities) if not delete else None, commercial_etag(website)
