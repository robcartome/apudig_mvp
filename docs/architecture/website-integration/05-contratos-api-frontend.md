# 05 — Contratos API y matriz de integración frontend

Estado B3: [integracion backend/Next y pruebas HTTP](11-entrega-b3.md) implementadas. R2 real y validacion visual en navegador siguen pendientes; no implica aceptacion integral ni habilita B4.

Fecha: 15/11/2026. Todos los contratos de integración de este archivo son **propuestos**, salvo los marcados existentes en develop o recuperables en websites_v0. No hay endpoints nuevos implementados por esta entrega.

Actualización B1: E0 (`GET /websites/current/`) está implementado y probado en PostgreSQL aislado. Los demás contratos continúan propuestos. Ver [informe B1](09-b1-implementacion.md) para autorización, capacidades disponibles y límites.

Actualización B2: E1–E6 y M0–M2 están implementados; E0 conserva su forma y comunica disponibilidad de publicación backend. Ver [entrega B2](10-entrega-b2.md) y [OpenAPI](b2-openapi.json). Los contratos públicos P y comerciales K/Q siguen pendientes; Next no fue modificado.

## Convenciones comunes

Base `/api/v1`, trailing slash, JSON UTF-8. UUID en strings; fechas ISO UTC; precios decimales strings y moneda explícita. No enviar company_id en el documento ni usarlo para autorización.

Perfiles usados por todas las tablas:

- **E:** autenticación JWT Bearer existente, Company del token + membresía actual revalidada; ruta `{id}` debe pertenecer a esa empresa. Sin empresa: denegar antes de consultar. IDs ajenos: 404; permiso insuficiente sobre recurso propio: 403. Cache-Control `private, no-store`, sin paginación salvo historial/media. Los errores siguen la tabla común.
- **P:** sin autenticación administrativa ni cookies; hostname normalizado en ruta/query resuelve dominio ACTIVE/verificado + Company activa + Website publicado + snapshot. Cache-Control `no-store` inicial; sin datos internos. Sitio desconocido/inactivo/no publicado: 404. No hay empresa por defecto.
- **W:** escritura E con `If-Match: "<editorial_revision>"` obligatorio; validación, autorización y concurrencia dentro de transacción. Respuesta editorial completa y ETag de nueva revisión. No modificar una parte del documento omitiendo la precondición.

Errores de la API nueva: `{code,message,fields?}`; fields usa rutas como `banners.0.title`. No cambiar globalmente los errores de APIs ERP existentes.

| HTTP | Código propuesto | Regla |
|---|---|---|
| 400 | VALIDATION / INVALID_HOSTNAME | Documento/query/tipo inválido; fields mapeable a pestañas |
| 401 | UNAUTHENTICATED / TOKEN_EXPIRED | JWT ausente o inválido; conservar desafío Bearer |
| 403 | FORBIDDEN / COMPANY_REQUIRED | Sin permiso/membresía/contexto; no ejecutar query global |
| 404 | NOT_FOUND | Recurso ajeno o no público; no confirmar existencia ajena |
| 409 | MEDIA_IN_USE / DOMAIN_CONFLICT | Conflicto de negocio, distinto del ETag |
| 412 | REVISION_CONFLICT | If-Match válido pero obsoleto; sin escritura ni publicación |
| 413 | PAYLOAD_TOO_LARGE | Body o archivo por encima del límite |
| 415 | UNSUPPORTED_MEDIA_TYPE | Archivo/tipo de contenido no admitido |
| 428 | PRECONDITION_REQUIRED | Falta If-Match en W |
| 429 | RATE_LIMITED | Límite de solicitudes, Retry-After |
| 503 | CONTENT_UNAVAILABLE / MEDIA_UNAVAILABLE | Fallo operativo; no responder demo/otra empresa con 200 |

`JWTAuthentication` actual no declara authenticate_header: DRF puede responder 403 para no autenticados. Asegurar y probar el 401 propuesto en la fachada nueva con desafío Bearer; no asumir que ya ocurre. `api.js` hoy pierde status/code/fields: ampliar un transporte específico del editor o preservar esos atributos con compatibilidad de sus consumidores.

CORS de la futura API editorial debe permitir If-Match y exponer ETag para llamadas desde Next en otro origen. Si se conserva no-store, no se necesita If-None-Match público inicial. ETag editorial corresponde a un Website concreto, no se reutiliza entre empresas.

## Descubrimiento y editor

Mantener la interfaz asíncrona `load / saveDraft / publish` del repositorio Next. Usar `/websites/current/` para descubrir UUID real; no resolver el alias `default` globalmente. La UI puede conservar scope interno mientras migra, pero las llamadas reales envían el UUID descubierto.

Capacidades derivadas de permisos reales: view/read.website, edit/manage.website, publish/publish.website, media/manage.website.media, domains/manage.website.domains. Lectura del editor se permite a quien posee alguna capacidad editorial; acciones independientes siguen separadas. No depender del nombre de rol que el cliente declare.

| ID | Método y ruta | Perfil / permiso | Request | Response / validación adicional | Paginación / tests |
|---|---|---|---|---|---|
| E0 | GET `/websites/current/` | E, alguna capacidad editorial | Sin body | `{id,companyId,templateKey,documentSchemaVersion,revision,capabilities}`; no crea Website en GET | No; A01/A02/A03 |
| E1 | GET `/websites/{id}/editor/` | E, capacidad de lectura editorial | Sin body | EditorRecord + ETag; draft y último published completos | No; A01/P01/C01 |
| E2 | PUT `/websites/{id}/draft/` | W, manage.website | `{document: WebsiteDocumentV3}` | EditorRecord + ETag; validar todo v3 y referencias; published sin cambios | No; P01/C01/C02/V01 |
| E3 | POST `/websites/{id}/publish/` | W, publish.website | Sin body | EditorRecord + ETag; publica únicamente draft guardado, snapshot transaccional | No; P02/P03/C01/C03 |
| E4 | GET `/websites/{id}/revisions/` | E, lectura editorial | `limit=20&offset=0`, máximo 100 | `{count,results:[RevisionSummary]}`; orden descendente por versión | Sí; P04/A01 |
| E5 | POST `/websites/{id}/restore/` | W, manage.website | `{revisionId:"uuid"}` | EditorRecord + ETag; revisión del mismo sitio, nueva revisión, no publicación | No; P04/C01/V02 |
| E6 | GET `/websites/{id}/preview/` | E, lectura editorial | Sin body; preview del draft guardado | `{websiteId,revision,content:WebsiteDocumentV3}`; no-store, X-Robots-Tag noindex | No; A01/P05 |
| M0 | GET `/websites/{id}/media/` | E, lectura editorial | `limit=20&offset=0`, máximo 100 | `{count,results:[MediaRecord]}` solo del sitio | Sí; M01/A01 |
| M1 | POST `/websites/{id}/media/` | E, manage.website.media | multipart `{file,kind,altText}` | 201 MediaRecord; 200 si dedup idéntico autorizado; no publica contenido | No; M01/M02/M03 |
| M2 | DELETE `/websites/{id}/media/{mediaId}/` | E, manage.website.media | Sin body | 204; 409 si referenciado por draft o revisión retenida; soft delete, sin borrado público accidental | No; M04/A01 |

Subir/eliminar media no cambia por sí mismo el documento ni su ETag; incorporar la referencia en draft sí requiere W. E5 target usa el UUID de revisión, distinto al contador global y a version por página. E4 puede añadir filtro por operación sin cambiar su orden estable. Auditoría visible reducida en EditorRecord y completa en historial; errores/reintentos no generan eventos falsos de éxito.

La edición de banners, avisos, identidad, SEO y secciones ocurre dentro de E2: no se necesitan CRUD separados que puedan dejar documento inconsistente. Si se habilitan rutas históricas `/settings/` o `/pages/.../sections/`, deben delegar al servicio de agregado y sus precondiciones; no constituyen una vía paralela sin revisión global.

### EditorRecord, RevisionSummary y MediaRecord

```json
{
  "schemaVersion": 3,
  "companyId": "<uuid de la empresa autenticada>",
  "websiteId": "<uuid>",
  "revision": 5,
  "draft": {"schemaVersion": 3},
  "published": null,
  "updatedAt": "2026-11-15T16:00:00.000Z",
  "publishedAt": null,
  "events": [{"action":"save","at":"2026-11-15T16:00:00.000Z","revision":5}],
  "capabilities": {"view":true,"edit":true,"publish":false,"mediaUpload":true,"realPublication":true}
}
```

draft/published están abreviados arriba: contienen el documento completo. published es null hasta publicar. events limita resumen a 20; acciones save/publish/restore y actor según permisos; la UI local actual solo contempla save/apply-demo, por lo que requiere adaptación. revision aumenta en guardar/publicar/restaurar. No hay retorno de tokens en datos editoriales.

RevisionSummary: `{id,version,editorialRevision,operation,at,actor:{id,name},sourceRevisionId?}`. El historial no devuelve borradores ajenos ni URLs privadas; restaurar revalida media y producto vigente, y devuelve errores si referencias ya no son publicables.

MediaRecord: `{id,websiteId,url,thumbnailUrl,mimeType,size,width,height,altText,kind}`. API usa referencias de media por ruta de campo para no alterar la forma del formulario: E2 admite además `mediaReferences:{"banners.banner-principal.imageUrl":"<media uuid>"}`. El servidor ignora la URL enviada para esos campos y deriva la canónica del recurso autorizado. Alternativamente puede resolver URLs propias a IDs internos; el DTO no acepta URLs externas como ownership. Es una ampliación del adaptador preparado que debe probarse en B2, sin añadir campos arbitrarios al documento v3.

Límites iniciales propuestos: JSON editorial 256 KiB sin inline; media PNG/JPEG/WebP máximo 5 MiB original, dimensiones fuente <=12000 y <=40 millones de píxeles (defaults actuales), procesamiento a WebP con variantes. Alinear el selector Next de 8 MiB con el límite real antes de activarlo. SVG/HTML/data URL rechazados en API; atributos alt conservados por referencia, no se ejecuta markup.

### Documento informativo mínimo completo para el primer hito

Valores de ejemplo, sin datos comerciales reales ni IDs demo. La imagen se adjunta por M1 y se referencia mediante mediaReferences; los campos de imagen pueden estar vacíos para probar primero texto/ilustración autorizada.

```json
{
  "schemaVersion": 3,
  "identity": {"name":"Empresa de prueba A","shortName":"Empresa A","location":"Lima","primaryColor":"#FF8000","logoUrl":"","announcement":"Atención comercial"},
  "contact": {"phone":"","secondaryPhone":"","email":"","whatsapp":"","address":"","hours":"","socials":{}},
  "seo": {"title":"Empresa de prueba A","description":"Información comercial de la empresa de prueba A."},
  "heroSlider": {"autoplay":true,"intervalMs":6000},
  "banners": [{"id":"banner-principal","enabled":true,"eyebrow":"BIENVENIDOS","title":"Banner A publicado","description":"Contenido de prueba guardado en Django.","ctaLabel":"Contacto","href":"/contact","imageUrl":"","mobileImageUrl":"","imageAlt":"","art":"drill"}],
  "announcements": {"ctaLabel":"Contacto","href":"/contact","items":[]},
  "specials": {"productIds":[]},
  "promotions": [],
  "sections": [
    {"type":"benefits","enabled":false,"title":"Beneficios"},
    {"type":"categories","enabled":false,"title":"Categorías"},
    {"type":"announcements","enabled":false,"title":"Avisos"},
    {"type":"specials","enabled":false,"title":"Especiales"},
    {"type":"featured","enabled":false,"title":"Productos"},
    {"type":"promotions","enabled":false,"title":"Campañas"},
    {"type":"about","enabled":true,"title":"Acerca de la empresa"}
  ]
}
```

Reutilizar el listado completo de reglas documentado en [01](01-auditoria-cruzada.md), derivado de validateWebsite; agregar validación backend de pertenencia, claves desconocidas, payload y media. No publicar defaults demo ni traducir `categories.enabled=false` en una navegación comercial vacía por error: en este hito la navegación comercial se deshabilita por capacidad de producto, no por el bloque legacy.

## Lectura pública y resolución

| ID | Método y ruta | Perfil | Request | Response / reglas | Paginación / tests |
|---|---|---|---|---|---|
| P0 | GET `/storefront/resolve/?hostname=...` | P | hostname sin esquema/puerto/ruta | `{websiteId,hostname,canonicalHostname,templateKey,locale,currency,revision}` desde publicación; ruta recuperable, DTO adaptado | No; H01/H02/H03 |
| P1 | GET `/storefront/sites/{hostname}/content/` | P | Sin body | PublicContent; nuevo contrato, fuente única de Home/layout/contacto | No; P01/P02/H02/S01 |
| P2 | GET `/storefront/sites/{hostname}/pages/{slug}/` | P | slug registrado | `{websiteId,revision,page:{slug,title,seo},content}`; recuperable, adaptar lectura al snapshot del agregado o página publicada | No; P03/H02 |
| P3 | GET `/storefront/sites/{hostname}/manifest/` | P, B4/SEO posterior | Sin body | Metadatos públicos y URLs publicadas; sin borradores/IDs internos Company | No; H02/S01 |

PublicContent: `{websiteId,hostname,canonicalHostname,templateKey,locale,currency,revision,publishedAt,commerceEnabled,content}`. `content` conserva propiedades v3 permitidas pero proyecta solo contenido visible; omite items/campañas deshabilitados o fuera de vigencia. Conserva la forma que necesitan los componentes. No incluye Company ID, draft, eventos, actor, storage_key ni preferencias ERP. revision pública identifica contenido publicado; no cambia al guardar draft.

Para proyectar secciones ocultas, filtrar su contenido sin revelar texto privado y mantener entradas de secciones con enabled=false si el renderer necesita estructura. La validación estricta del documento editorial íntegro no se ejecuta contra esa proyección recortada como si fuera un draft; usar validador público específico. Hero y avisos pueden tener arrays vacíos. Campañas usan reloj servidor y límites inclusivo inicio/exclusivo fin.

`commerceEnabled=false` en B3: no publicar IDs demo, precios ni CTA de cotización activa. Publicar identidad/contacto no debe convertir automáticamente el carrito demo en real. En Next, mantener noindex del piloto hasta QA y decisión de activación SEO; canonical solo desde dominio registrado. Preview siempre noindex/no-store. Configuración de identidad y contenido se resuelven juntos para evitar mezcla de revisiones.

## Catálogo B4 y carrito B5

Preferir rutas recuperables por hostname; adaptar servicios Next preparados, sin tocar `/catalog` laboral. Estas ampliaciones se diseñan ahora y se implementan después del hito informativo.

| ID | Método y ruta | Perfil | Request | Response / validación | Paginación / tests |
|---|---|---|---|---|---|
| K0 | GET `/storefront/sites/{hostname}/products/` | P | search, category repetible, brand repetible, min, max, ordering, limit, offset | `{websiteId,count,limit,offset,results:[ProductDTO],facets}` | Default24, máximo100; K01/K02/K03 |
| K1 | GET `/storefront/sites/{hostname}/products/{id}/` | P | UUID de Product publicado; slug opcional compatible | `{websiteId,product:ProductDTO}`; 404 ajeno/inactivo/no publicado | No; K01/S01 |
| K2 | GET `/storefront/sites/{hostname}/categories/` | P | limit/offset | `{websiteId,count,results:[CategoryDTO]}` | Default100/máximo100; cargar páginas para navegación; K02 |
| K3 | GET `/storefront/sites/{hostname}/brands/` | P | limit/offset | `{websiteId,count,results:[{id,name,productCount}]}` | Default100/máximo100; K02 |
| K4 | GET `/websites/{id}/catalog-product-options/` | E, lectura editorial, B4 | search, limit/offset | IDs/nombre/SKU de productos de Company para selección editorial; sin costos | Default24/máximo100; A01/K01 |
| K5 | GET/PATCH `/websites/{id}/catalog-settings/` | E, read/manage.website | PATCH lista autorizada, almacenes y política | Política CMS; validar lista.company y almacén.store.company | No; K01/K04 |
| K6 | GET/POST `/websites/{id}/products/` | E, read/manage.website | POST productId, isPublished, copy/posición | WebsiteProduct, FK existente; publicar además exige publish.website | List24/máximo100; K01/K04 |
| K7 | PATCH/DELETE `/websites/{id}/products/{publicationId}/` | E, manage.website | Cambios de vínculo/copy; no Product maestro | Vínculo actualizado /204; cambio de publicación exige publish.website | No; K01/K04 |
| Q0 | POST `/storefront/sites/{hostname}/cart/quote/` | P + rate limit | QuoteRequest | QuoteResponse, no-store; nunca crea venta ni reserva | No, máximo50 líneas; Q01–Q05 |

K5–K7 tienen estado comercial propio y no deben evadir autorización/invalidation; definir su contador/precondición comercial al implementar B4, independiente del ETag editorial. Las referencias del contenido se validan en publicar y se ocultan si un producto se retira. Evitar prometer atomicidad de precio/stock junto a publicación editorial: se consultan en vivo bajo política comercial.

ProductDTO: `{id,name,sku,brand:{id,name}|null,category:{id,name}|null,unit,unitId,price,original_price,currency,description,image_url,image_alt,images,availability,badge}`. price nullable decimal string; original_price null mientras no exista fuente válida. availability en `available/unavailable/unknown`; badge solo editorial autorizado. Nunca devolver price_purchase/costos/márgenes/supplier_codes/listas internas/stock por almacén. CategoryDTO: `{id,name,description,icon,image_url,parent_id,productCount}`; icon/imagen/jerarquía opcionales donde el modelo actual no los tenga, sin inventar clasificaciones.

Filtros: OR dentro de categorías/marcas, AND entre grupos; rangos inclusivos y válidos min<=max; búsqueda por nombre/SKU y campos públicos autorizados, sin códigos privados de proveedor. Orden frontend name/name-desc/price-asc/price-desc/discount se traduce a name/-name/price/-price/discount; precios nulos al final y UUID como desempate estable. Descuento se habilita solo con fuente real, nunca calcula promociones desde banners. Facets cuentan todo el conjunto publicable con búsqueda/precio y demás filtros aplicados, excluyendo el propio grupo al contar opciones de categoría o marca; documentar ceros. Categorías de navegación pueden devolver todo el conjunto público, sin confundirlo con facets del resultado.

QuoteRequest: `{lines:[{product_id,quantity,unit_id?,notes?}],previous_quote_token?}`. quantity entero 1–999, 1–50 líneas únicas por producto/unidad; B5 inicial una unidad de venta válida por producto y política explícita de conversiones; no confiar en unit_id ajeno ni factor del cliente. Notas <=240, texto plano; nunca generan variantes/stock. No se aceptan precios como autoridad. Reducir límite UI de 200 a 50 de forma comunicada sin truncado silencioso de un carrito existente.

QuoteResponse: `{version,websiteId,quote_id,quote_token,quoted_at,expires_at,currency,total,has_changes,can_submit,lines}`; líneas `{product_id,quantity,status,unit_id?,unit?,price?,subtotal?,availability?}` y nombre/SKU/imagen únicamente si son públicos del sitio. REMOVED no revela campos descriptivos ajenos; OUT_OF_STOCK/UNKNOWN conservan política explícita, sin promesa de entrega. Total Decimal solo de líneas cotizables. Firma y TTL del histórico son reutilizables, pero la firma no crea un documento ERP ni debe incluirse en WhatsApp.

`has_changes` histórico solo detecta retirados/agotados: no se debe afirmar detección de cambio de precio sin referencia previa. Para comparar precios usar previous_quote_token firmado y vigente del mismo sitio o comparación visual del cliente contra la respuesta recalculada; nunca confiar en precio previo enviado sin verificar. Si no hay referencia, informar primera cotización, no asumir que nada cambió. Moneda e impuestos coherentes con `pricing.py` y las reglas comerciales existentes. Rate limit inicial propuesto 20/min por sitio/IP, TTL900s, cache compartida si hay varias instancias; no configurar infraestructura ahora.

## Matriz por pantalla: conexión prevista

Requests/responses/auth/permiso y errores se definen por ID arriba; dependencias y riesgos aquí completan la matriz. Fuentes detalladas en [01](01-auditoria-cruzada.md).

| Pantalla / componente | Servicio actual -> futuro | Operación / endpoint y estado | Request -> response | Auth / permiso | Dependencias / riesgo |
|---|---|---|---|---|---|
| Home / StoreHome / StoreHero | store.js demo -> fuente pública SSR | P1 nuevo | hostname -> PublicContent | Público P | B1/B2; pasar content explícito, sin defaults demo |
| Header/Footer | getStore/categorías -> P1/K2 | Identidad/contacto/navegación | hostname -> content/K2 | Público P | Snapshot único; comercio apagado B3 |
| About | getStore + JSX -> P1 | Identidad y SEO | hostname -> content | Público P | Cuerpo hardcodeado no tiene editor; no prometer CMS completo |
| Contact | getStore -> P1 | Contacto publicado | hostname -> content.contact | Público P | No exponer datos fiscales ni números ficticios |
| Shop / StoreCatalog | array + filtros -> storefrontProductsService | K0 ausente develop, parcial histórico | filtros -> Page/ProductDTO/facets | Público P | B4; no filtrar página parcial en memoria |
| Ficha / ProductPurchase | getStorefrontProduct -> servicio público | K1 recuperable adaptado | ID -> product wrapper | Público P | B4; mantener HTTP404 real, mapa imagen/availability |
| Carrito / CartProvider | array/localStorage -> resolver IDs y Q0 | Revalidar selección | lines -> QuoteResponse | Público P | B5; no eliminar IDs fuera de página ni confiar en totales locales |
| WhatsApp / CartPage | buildQuotationMessage -> resultado Q0 | Mensaje de cotización vigente | Q0 -> enlace validado | Público P | Número publicado; sin venta/reserva; no enviar mensaje automáticamente |
| Editor identidad/contacto/SEO | repositorio local -> createDjangoWebsiteRepository | E0/E1/E2 nuevos sobre CMS recuperado | document -> EditorRecord | E/W, lectura/edición | B2; mapear status/fields y permisos |
| Editor banners/avisos | WebsiteEditor/ShowcaseEditor -> E2/M1 | Guardar arrays y subir media | document + referencias -> EditorRecord | W/manage; media aparte | B2; data URL local no aceptable en API |
| Campañas/secciones/especiales | repositorio local -> E2/K4 | Guardar orden, visibilidad, referencias | documento v3 -> EditorRecord | W/manage | B2 sin referencias comerciales; B4 IDs reales |
| Publicar | apply local -> publish API | E3 | If-Match -> EditorRecord | W/publish.website | Atomicidad y captura íntegra del agregado |
| Preview iframe | WebsitePreview local -> E6 + postMessage | Preview guardado/formulario válido | sesión/document -> preview | E/lectura | No-cache, noindex; postMessage no es autorización backend |
| Historial/restaurar | eventos locales -> E4/E5 | Historial y restaurar | revisionId -> nuevo draft | E/W lectura/edición | La UI completa de historial será ampliación acotada; no publicar al restaurar |
| Login/empresa | authService actual | /auth/token, me, select-company, refresh existentes | email/password o company_id -> tokens/perfil | Auth existente | Sin segundo auth; probar expiración y pérdida de membresía |
| Catálogos laborales | productsService actual | /catalog y /catalog/private existentes | search/limit/offset -> total/results | Contrato legado | Mantener forma/rutas; adaptar tenant seguro sin imponer ?site= a ciegas |

## Rutas administrativas históricas fuera del primer hito

Dominios: recuperar GET/POST `/websites/current/domains/` y PATCH `.../{domainId}/primary/` con perfil E y manage.website.domains para mutaciones. POST `{hostname,kind}` devuelve registro PENDING y token de verificación una sola vez; GET no vuelve a mostrar secreto; primario solo ACTIVE/verificado. 400/403/404/409, no-store, listado paginado20/máximo100 al adaptar; tests H01/H04. No hay permiso para marcar un dominio ACTIVE enviando status en PATCH. La comprobación DNS/control real necesita un servicio operativo autorizado: no está demostrada por generar el token.

Menús: existen GET/POST `/websites/current/menus/`, GET/PATCH por ID, PUT items `{expected_version,items}` y POST publish `{expected_version}` en websites_v0. Conservar como referencia B2 posterior; no exponer dos modos de publicación incoherentes. Antes de habilitar, integrar a ETag/snapshot global, validar enlaces/páginas mismo sitio y profundidad, y definir requests/responses en OpenAPI con pruebas P02/A01/V01. No hay solicitud de rediseñar Next ni crear editor de menús en esta intervención.
