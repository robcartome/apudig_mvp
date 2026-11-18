from decimal import Decimal

from apps.inventory.pricing import money


def sale_unit(publication, unit_id, label, factor):
    price = publication.offer_amount
    price = money(price * factor * publication.offer_tax_multiplier) if price is not None else None
    availability = publication.offer_availability
    if availability != "unknown":
        availability = "available" if publication.offer_stock >= factor else "unavailable"
    return {
        "unitId": str(unit_id), "unit": label,
        "price": format(price, ".2f") if price is not None else None,
        "availability": availability,
    }


def product_data(publication, website, *, detail=False):
    product = publication.product
    result = {
        "id": str(product.pk), "name": publication.offer_name, "sku": product.sku,
        "description": publication.commercial_description or product.description,
        "brand": {"id": str(product.brand_id), "name": product.brand.name} if publication.public_brand_id else None,
        "category": {"id": str(product.category_id), "name": product.category.name} if publication.public_category_id else None,
        "unitId": str(publication.offer_unit_id), "unit": publication.offer_unit,
        "currency": website.currency, "price": format(publication.offer_price, ".2f") if publication.offer_price is not None else None,
        "priceIncludesTax": True, "original_price": None,
        "image_url": product.image or None, "image_alt": publication.offer_name, "images": product.image_urls,
        "availability": publication.offer_availability, "badge": "Destacado" if publication.is_featured else "",
    }
    if detail:
        units = {product.unit_id: sale_unit(publication, product.unit_id, product.unit.name, Decimal("1"))}
        for conversion in product.catalog_sale_units:
            if conversion.unit_id == product.unit_id and conversion.conversion_factor != 1:
                continue
            units[conversion.unit_id] = sale_unit(publication, conversion.unit_id, conversion.unit.name, conversion.conversion_factor)
        result.update(saleUnits=list(units.values()), seoTitle=publication.seo_title, seoDescription=publication.seo_description)
    return result
