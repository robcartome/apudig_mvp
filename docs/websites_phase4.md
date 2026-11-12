# Sitios web — Fase 4

La Fase 4 añade un catálogo público SSR/ISR que sólo expone productos
vinculados explícitamente al sitio mediante `WebsiteProduct`.

## Migración

```powershell
python manage.py migrate
```

La migración `0005_websitecatalogsettings_websiteproduct` crea:

- `WebsiteCatalogSettings`: lista de precios predeterminada, almacenes
  autorizados, visibilidad de agotados y tamaño de página;
- `WebsiteProduct`: vínculo único sitio/producto, slug público, copy comercial,
  SEO, posición, destacado y estado de publicación.

La migración crea configuración vacía para los websites existentes. No publica
productos automáticamente: la ausencia de vínculos es deliberadamente
fail-closed.

## Política de datos públicos

- El producto debe pertenecer a la misma empresa del website y estar activo.
- `is_published=True` es obligatorio para lista, búsqueda, filtros y detalle.
- El precio usa la lista específica del vínculo, luego la lista predeterminada
  del website y finalmente `Product.price_sale`.
- El stock se suma únicamente en almacenes autorizados y se transforma en
  `AVAILABLE`/`OUT_OF_STOCK`; nunca se publican cantidades ni nombres de almacén.
- Si no se seleccionan almacenes, la disponibilidad es `UNKNOWN`.
- Nunca se serializan costo, precio de compra, proveedores, márgenes o listas
  internas.

## API CMS

- `GET/PATCH /api/v1/websites/current/catalog-settings/`
- `GET /api/v1/websites/current/catalog-product-options/`
- `GET/POST /api/v1/websites/current/products/`
- `GET/PATCH/DELETE /api/v1/websites/current/products/{id}/`

Editar vínculos requiere `manage.website`. Cambiar `is_published` requiere
además `publish.website`. Productos, listas de precios y almacenes de otra
empresa se rechazan.

## API pública

- `GET /api/v1/storefront/sites/{hostname}/products/`
- `GET /api/v1/storefront/sites/{hostname}/products/{slug-or-uuid}/`
- `GET /api/v1/storefront/sites/{hostname}/categories/`
- `GET /api/v1/storefront/sites/{hostname}/brands/`

La lista acepta `search`, `category`, `brand`, `ordering`, `limit` y `offset`.
El contrato heredado `/api/v1/catalog/products/?site=...` permanece disponible
durante la transición.

## Caché y SEO

Las mutaciones invalidan `site:{website_id}`, `catalog:{website_id}` y las
etiquetas de hostname. El manifiesto público incluye productos publicados para
el sitemap. Next genera canonical, Open Graph, JSON-LD `Product` y
`BreadcrumbList`; páginas de filtros y búsqueda usan `noindex,follow`.

## Rollback

Revertir `0005` elimina configuración y vínculos públicos, pero no modifica
productos, precios, almacenes ni stock del ERP. Antes de revertir, exportar los
slugs y textos comerciales si deben conservarse.

## Verificación

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.inventory.tests.test_catalog_api apps.websites.tests --keepdb --noinput
```

