# 02 — Comparación de websites_v0 con develop

Fecha: 15/11/2026. Inspección estática de `a9d3a3a` frente a `c8296b7`. Ningún componente histórico se declara probado en ejecución por esta auditoría.

Consultar las fuentes ausentes del checkout con `git show websites_v0:apps/websites/models.py` y comandos equivalentes. No confundir `apps/web` (vistas del ERP) con `apps/websites` (CMS histórico).

Clasificación: **A** reutilizable directamente en concepto/contrato indicado, pendiente de regresión; **B** reutilizable con adaptación; **C** no recuperar tal como está; **D** funcionalidad ausente que requiere desarrollo. Una fila puede separar base reutilizable de una ampliación ausente.

| Componente / fuente en websites_v0 | websites_v0 | develop | Decisión | Riesgo / adaptación |
|---|---|---|---|---|
| models.py:Website | UUID, OneToOne Company, slug, estado, ecommerce | Sin fuentes CMS | B | Reutilizar una web por empresa; extender control editorial global, no crear segundo Website |
| models.py:WebsiteDomain / normalize_hostname | IDNA, unicidad, estado, verificación, dominio primario | Ausente | A/B | Reutilizar normalizador/constraints; completar flujo de verificación y controlar proxy/activación |
| models.py:WebsiteSettings | Tema, contacto, SEO, media | Ausente | B | Faltan shortName/location/announcement, segundo teléfono, hours texto, red X; snapshot público obligatorio |
| models.py:WebsitePage / WebsiteSection | HOME y páginas estándar/contacto; bloques ordenados | Ausente | B | Mapear documento v3 sin duplicar draft en otra tabla JSON |
| models.py:WebsitePageRevision | Snapshot inmutable por página/version | Ausente | B | Reutilizar; cubrir documento completo e historial de guardados/restauraciones, no solo publicación |
| models.py:WebsiteMedia | Archivo R2, metadata, hash, soft-delete | Ausente | B | Ownership, referencias desde snapshots, race de checksum y limpieza de archivos huérfanos |
| models.py:WebsiteMenu / WebsiteMenuItem | Árbol de un nivel, draft/publicación | Ausente | B | Sin editor equivalente Next; aplazar UI, incorporar snapshot coherente si se expone |
| models.py:WebsiteCatalogSettings / WebsiteProduct | Política y vínculo explícito al maestro ERP | Ausente | B, B4 | No crear productos paralelos; reforzar validaciones en servicios, no solo serializer |
| blocks.py | 8 bloques v1 tipados | Ausente | B | Hero simple no representa slider; faltan avisos, especiales, campañas y opciones v3 |
| services.py:replace_page_sections / publish_page | atomic + select_for_update + expected_version | Ausente | B | Conservar bloqueo, abarcar todo el agregado y traducir a If-Match |
| services.py:build_page_snapshot | Página/SEO y secciones habilitadas | Ausente | B | No incluye identidad/contacto; no conserva secciones ocultas al restaurar; hace falta snapshot editorial íntegro |
| services.py:restore_page_revision | Recupera secciones y atributos de página | Ausente | B | Debe recuperar también settings, slider, referencias y elementos ocultos; nunca publicar implícitamente |
| services.py:preview firmado | Token temporal ligado a draft_version | Ausente | B, posterior | Primera entrega puede usar sesión/JWT editorial; no exponer drafts por query pública |
| services.py:revalidation | HTTP saliente tras commit y tags por sitio | Ausente | B | No hay Route Handler consumidor en el frontend actual; empezar no-store, añadir entrega/reintentos después |
| selectors.py:get_company_website | Falla si no hay company_id | Ausente | A | Anteponer membresía y permisos; no tomar tenant del formulario |
| selectors.py:get_public_website_by_hostname | Empresa activa, website publicado y dominio activo/verificado | Ausente | A/B | Reutilizar predicados; 404 uniforme y snapshot, sin website por defecto |
| selectors.py:get_public_website_products | Publicación explícita, precio y disponibilidad de almacenes | Ausente | B, B4 | Revalidar company en todas las relaciones y moneda/UOM; cantidades nunca públicas |
| media_storage.py | Reutiliza inspección y upload procesado | R2 y Pillow de productos disponibles | B | El commit añade upload_processed_image al módulo compartido; no importar helper inexistente en develop |
| api/v1/websites/urls.py y vistas | /websites/current/, settings/pages/media/menus/products | No montadas | B | Fachada compatible con Next; no activar escrituras históricas que evadan concurrencia global |
| api/v1/catalog:StorefrontResolveAPIView | Resolución pública de identidad/configuración | Ausente | B | Lee settings vivos: debe representar únicamente publicación |
| StorefrontProductList/Detail | Catálogo seguro dedicado por hostname | Ausente | B, B4 | Adaptar DTO/paginación; filtros múltiples, rango, facets y descuentos faltan |
| StorefrontCartQuoteAPIView / throttles.py | Recalcula hasta 50 líneas, firma snapshot, no crea venta | Ausente | B, B5 | Falta UOM de venta; límites difieren de Next; has_changes no detecta por sí solo precio anterior |
| Cambios LegacyStorefrontMixin en /catalog | Exige ?site= y cambia serialización/filtrado | Contrato laboral sin ese parámetro | C como reemplazo directo | Mantener consumidor existente; resolver vulnerabilidades mediante adaptación explícita, sin fallback global |
| Cambios inventory/views.py | Endurece productos con permiso y tenant | AllowAny en listas/detalle | B, regresión separada | Necesarios de revisar, pero afectan consumidores del ERP; no acoplar a un merge total |
| api/v1/permissions.py / base.py | HasCompanyPermission, get_required_company_id | IsCompanyUser solo contexto | B | Reutilizar ideas; denegación específica website sin fallback permisivo por módulo ausente |
| signals.py | Crea settings/home/menús/catalog settings | Ausente | B | Bootstrap consistente/idempotente; no publica ni crea dominios activos automáticamente |
| migrations/0001–0006 | Cadena histórica completa | Ninguna fuente websites instalada | B condicionada a BD | Dependencias existen en el árbol; historial aplicado y tablas reales no verificados |
| tests/test_api.py / test_models.py | Tenant, permisos, publicación, preview, media, menú, catálogo | Tests ERP existentes | B | Recuperar y ampliar; conservar pruebas de contrato laboral actuales, no reemplazarlas |
| Registro de plantillas | Solo ecommerce/schema 1, corporate rechazado | Ausente | B | Registro extensible por plantilla/versión; no activar corporate sin renderer/validación |
| Fachada v3, errores de campo, ETag global | No implementada | Ausente | D | Diseñar endpoints compatibles con createDjangoWebsiteRepository |
| Auditoría de todas las operaciones | created_by/updated_by y revisiones de publicación | Sin auditoría CMS | D | Evento append-only propio del dominio, no otro modelo de contenido |
| Publicación coherente de settings + secciones | Settings actuales independientes de snapshot | Ausente | D sobre modelos B | Lectura pública de un único snapshot; evita fugas de borrador |

## Diferencias contractuales concretas

| Next actual/preparado | Código histórico | Resolución propuesta |
|---|---|---|
| schemaVersion:3 documento único | schema_version:1 por bloque y páginas | Distintas versiones: adaptador de agregado; no renumerar bloques históricos |
| websites.view_website/change_website/publish_website | read.website/manage.website/publish.website | Capacidades desde servidor y mapeo de UI a permisos propios ERP |
| /websites/{id}/editor, draft, publish | /websites/current/pages/{id}/sections, publish | Fachada nueva sobre servicios recuperados; current solo descubre website |
| If-Match y 412/428 | expected_version y 409 VERSION_CONFLICT | API nueva con ETag; adaptar llamadas internas y errores legacy sin cambiar clientes ajenos |
| /stores/{storeId}/products | /storefront/sites/{hostname}/products | Preferir ruta histórica por hostname y UUID estable en respuesta |
| count/store_id/product wrapper | total/limit/offset/results y detalle plano | DTO de integración normalizado en fachada/servicio público, sin tocar catalog laboral |
| available/unavailable/unknown | AVAILABLE/OUT_OF_STOCK/UNKNOWN | Mapear estados, nunca deducir disponibilidad desde datos privados en JSX |
| image_url | image + thumbnails | Mapear a URL y galería permitida; frontend image es fallback artístico |
| categorías/marcas múltiples + min/max/discount | get singular y orden name/-name/price/-price | Extender consulta global; no filtrar una página aislada |
| Carrito local de hasta 200 líneas / notas | Cotización máximo 50 / sin notas | Límite público 50 comunicado en UI, conservar notas y no tratarlas como datos ERP |

## Migraciones y recuperación

El grafo histórico y sus dependencias se detallan en [04](04-modelo-datos-y-migraciones.md). La presencia de .pyc no prueba migraciones aplicadas. No copiar solo 0001 ni saltar 0005 para evitar catálogo: 0006 depende de 0005 y el código histórico referencia esos modelos.

No se recomienda merge/cherry-pick completo de a9d3a3a: además del CMS modifica catálogo laboral, permisos y vistas de inventario. Recuperación posterior por componentes revisados, con cadena de migraciones conciliada y pruebas de ambos contratos. El tamaño del commit no permite asumir que todo sea compatible aunque derive del mismo HEAD develop.
