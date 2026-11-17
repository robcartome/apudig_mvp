# B4-A — Auditoría y diseño del catálogo e-commerce

Fecha: 16/11/2026. Diseño propuesto sobre backend `websites_backend@9e9eaf5` y frontend `mvp_website@83eb3ac`. No se implementan endpoints, migraciones ni contratos comerciales nuevos en esta entrega. B3-A continúa sin aceptación integral; ver [validación actual](13-validacion-b3-a.md).

## Separación del CMS y comercio

| Dominio | Fuente de verdad | Cambio visible |
|---|---|---|
| Identidad, banners, contacto, SEO y configuración de secciones | Documento editorial y revisión publicada CMS | Solo después de publicar una revisión completa |
| Inclusión/retirada de producto y destacados comerciales | WebsiteProduct, FK al producto ERP | Tras operación comercial autorizada, sin republicar todo el CMS |
| Nombre/imagen/unidad base del producto | Product, Unit y ProductUnit del ERP; copy opcional ya existente en WebsiteProduct | En la próxima lectura pública autorizada |
| Precio | ProductPrice/PriceList autorizada y reglas inventory/pricing.py | En la próxima lectura tras confirmar la transacción ERP |
| Disponibilidad | StockByWarehouse, solo almacenes públicos autorizados | En la próxima lectura; sin promesa de reserva |

Ejemplo: cambiar el precio ERP de una válvula debe actualizar K0/K1 y la cotización comercial en su siguiente lectura, sin ejecutar E3. Cambiar su banner exige E2/E3. En una Home, primero se lee el snapshot informativo y luego se resuelven sus referencias comerciales contra la oferta pública actual. Retirar un producto lo oculta aunque su ID permanezca en una revisión histórica.

No copiar precios, costos o stock al documento CMS. ETag editorial y precondición comercial son independientes. Un snapshot CMS no garantiza atomicidad con el inventario o el precio de otra transacción. La cotización debe revalidarlos antes de preparar WhatsApp.

## Modelos y servicios reales

| Fuente actual | Reutilizable | Trabajo necesario |
|---|---|---|
| inventory.Product | Maestro con Company, SKU, unidad, categoría, marca, precio de venta, actividad e imágenes | Seleccionar siempre por empresa y publicación explícita; no exponer columnas de costo |
| inventory.Unit / ProductUnit | Unidad global y conversión por producto, factor positivo, precio de venta por unidad, unidad de venta por defecto, active | Exponer solo unidades permitidas del mismo producto; definir reglas de cantidad/fracción |
| inventory.PriceList / ProductPrice | Lista por empresa, actividad, moneda, importe, prices_include_tax | Seleccionar una sola lista autorizada; no devolver todas las listas |
| inventory.pricing.py | resolve_commercial_price, tax_rate_for_company, gross_from_unit_value, Decimal/redondeo | Acotar referencias/moneda antes de llamar; revisar fallback e impuestos |
| inventory.Category / Brand | Entidades por Company, con actividad | Categorías son planas; no hay parent, imagen o icono de categoría persistidos |
| Product.image_key y otras cinco claves | Hasta tres imágenes y sus thumbnails; propiedades con URL pública R2 | No existe ProductImages separado; reutilizar esas claves sin mover objetos |
| StockByWarehouse / Warehouse / Store | Stock por producto y almacén; propiedad de empresa vía Store | Solo sumar almacenes seleccionados, activos y de la empresa; no devolver sus nombres/ubicaciones |
| websites.WebsiteProduct | Vínculo único Website/Product, is_published, is_featured, position, slug, copy/SEO y price_list opcional | Ya hay control de publicación; no hace falta otro maestro o flag duplicado en Product |
| websites.WebsiteCatalogSettings | Lista por defecto, almacenes M2M, show_out_of_stock, products_per_page | Agregar servicios autorizados y validar cambios M2M; no habilitar comercio por existir el registro |

La inspección de integridad local, solo lectura, no encontró productos sin empresa ni relaciones cruzadas no nulas en categoría/marca/precios/stock. Es una fotografía de los datos actuales, no una garantía del esquema: algunas FK admiten Company nula y ProductPrice.clean no sustituye validaciones de cada ruta de escritura.

No se proponen migraciones para publicación de productos: WebsiteProduct ya existe. Para **subcategorías reales**, la opción compatible a evaluar es añadir Category.parent nullable con validación de misma empresa, ausencia de ciclos y tratamiento de datos existentes. Requiere diseño y aprobación de esa necesidad antes de migrar el maestro ERP. Mientras no exista, el contrato debe declarar parent_id=null y UI plana, sin inventar jerarquías por nombre. Esa limitación debe resolverse antes de prometer subcategorías funcionales en B4-C.

## Hallazgos priorizados

| Prioridad | Hallazgo de código | Consecuencia / acción |
|---|---|---|
| P0 | CatalogProductList/Detail son AllowAny y company_required=False; get_products no filtra si no recibe empresa | Una consulta anónima sin contexto puede ser global. No reutilizar estas vistas como storefront seguro |
| P0 | CatalogProductDetailSerializer devuelve price_list con todas las listas activas, stock_by_warehouse y supplier_codes | El DTO no satisface confidencialidad comercial. Crear proyección explícita con allowlist de campos |
| P0 | Catálogo privado usa autenticación y el mismo mecanismo de contexto opcional | Revalidar acceso vigente/empresa antes de consultar o mostrar costos. Investigar/remediar de forma compatible por consumidor |
| P1 | Stock legado suma sin política Website de almacenes activos/autorizados | Puede representar inventario de locales no publicables y disponibilidad incorrecta |
| P1 | resolve_commercial_price vuelve a Product.price_sale si falta una fila de lista y puede usar ProductUnit.sale_price en PEN | No llamar a ciegas: una ausencia de precio público no debe abrir un fallback no autorizado |
| P1 | Búsqueda ERP incluye código/nombre de proveedor | En storefront usar únicamente campos autorizados (nombre/SKU); no devolver ni usar información privada como superficie de descubrimiento |
| P1 | Servicios Next preparados usan /stores/{storeId}, store_id y paginación count | No coinciden con rutas por hostname ni con el legado total; adaptar el cliente antes de conectarlo |
| P1 | Filtros/carrito actuales trabajan sobre arrays completos; normalizador pierde unitId/moneda | No aplicar filtros globales ni validar el carrito contra una única página parcial; adaptar contrato y transporte |

Los hallazgos proceden de fuentes, no de una extracción HTTP de productos privados. No se hicieron consultas anónimas de catálogo para volcar datos reales. Preservar las rutas laborales no justifica mantener estas debilidades indefinidamente: preparar una remediación separada con pruebas de contratos y contexto para `/catalog` y `/admin/catalog_admin`, antes de exposición pública. Esta auditoría no declara esas vulnerabilidades corregidas.

## Pipeline propuesto y política comercial

1. Resolver hostname registrado mediante el selector público existente y recuperar internamente su Website/Company. Nunca aceptar company_id público como autorización ni elegir la primera empresa.
2. Filtrar WebsiteProduct por ese Website, is_published=True y Product.active=True, product.company_id igual a la empresa. Aplicar condiciones equivalentes en detalle, conteos, facets, categorías, marcas y selección de destacados. Excluir relaciones secundarias inválidas en vez de seguir FK de otro tenant.
3. Elegir price_list explícita del vínculo o default_price_list del Website, activa y de esa Company. Propuesta inicial: sin lista/fila de precio autorizada, devolver price=null; no usar automáticamente price_sale o sale_price de la unidad. La visibilidad de precio y cualquier fallback de venta ERP deben acordarse como política explícita, no deducirse de que exista un importe.
4. Respetar prices_include_tax. El helper de resolución devuelve el importe sin normalizar esa bandera; convertir solo si procede con las funciones canónicas y el impuesto de empresa. No aplicar IGV dos veces ni asumir siempre18%. Decimal en servidor, string decimal en DTO; moneda coherente con la lista y el sitio.
5. Usar la unidad de venta autorizada de ese producto. En B4-B definir si la primera oferta usa solo unidad base o unidad de venta por defecto; B4-D añadirá selección de otras unidades válidas. Factores/costos de compra nunca vienen del navegador. Los servicios o conceptos sin inventario requieren disponibilidad unknown/según política, no una afirmación de agotado por stock0.
6. Agregar stock únicamente de los almacenes expresamente asociados y activos, con Store activa y misma Company. Propuesta fail-closed: selección vacía significa disponibilidad unknown, nunca todos los almacenes. No reservar stock ni prometer fecha de entrega. Decidir tratamiento de negativo y show_out_of_stock antes de activar compra/cotización.
7. Serializer público propio con campos permitidos; select_related/prefetch y subqueries acotadas al tenant. Probar consultas y evitar N+1 de impuestos, precios, unidades y stock. Filtrar/ordenar antes de paginar; precio de ordenación debe ser el mismo de presentación.

Cache inicial no-store en todas las lecturas comerciales. Así, la próxima petición tras cambiar precio/stock ERP toma el dato actual. Cuando se incorpore caché, su clave incluirá Website, moneda, política comercial, filtros y página; las mutaciones ERP de precios/unidades/stock/publicación comercial deben invalidar o vencer esa caché mediante mecanismo on_commit y política medible. No usar editorial_revision como única versión de precio/stock. No se implementa esa infraestructura ahora.

## Contratos propuestos, aún no implementados

Base `/api/v1/`, trailing slash. Reutilizan el diseño 05; esta sección precisa decisiones pendientes sin alterar endpoints actuales.

| Contrato | Método/ruta | Forma y reglas |
|---|---|---|
| K0 | GET `/storefront/sites/{hostname}/products/` | websiteId,count,limit,offset,results,facets. search, category/brand repetibles, min/max, ordering, featured opcional; limit24/máx100 |
| K1 | GET `/storefront/sites/{hostname}/products/{productId}/` | websiteId,product; UUID de Product publicado en ese Website, 404 ajeno/inactivo/retirado |
| K2 | GET `/storefront/sites/{hostname}/categories/` | websiteId,count,results; solo categorías activas con publicaciones elegibles; parent_id=null mientras no exista jerarquía |
| K3 | GET `/storefront/sites/{hostname}/brands/` | websiteId,count,results; solo marcas públicas del conjunto elegible |
| K4 | GET `/websites/{websiteId}/catalog-product-options/` | Sesión JWT y permisos Website actuales; opciones del ERP de la Company, sin costos |
| K5 | GET/PATCH `/websites/{websiteId}/catalog-settings/` | Lista/almacenes/política; validar todas las FK/M2M y una precondición comercial independiente |
| K6/K7 | GET/POST `/websites/{websiteId}/products/`, PATCH/DELETE `.../{publicationId}/` | Crear/editar/retirar vínculo; jamás duplicar Product o eliminarlo. Cambio de publicación exige publish.website además de gestión |
| Cotización futura | POST `/storefront/sites/{hostname}/cart/quote/` | B4-D según la solicitud actual: revalidar tenant/unidades/cantidades/precios/disponibilidad; no crear SalesQuotation/venta/reserva |

ProductDTO conceptual: id, name, sku, description, brand{id,name}|null, category{id,name}|null, unitId, unit, currency, price:string|null, original_price:null, image_url, image_alt, images, availability (`available/unavailable/unknown`) y badge solo autorizado. Añadir lista de unidades de venta cuando se implemente esa selección. No entregar price_purchase, inventory_unit_cost, last_purchase_unit_value, purchase_price de conversiones, márgenes, proveedores, todas las listas ni almacenes/movimientos. `original_price` y orden por descuento permanecen deshabilitados hasta contar con una fuente comercial real.

CategoryDTO: id,name,parent_id,productCount; decoración visual opcional según fuente autorizada, sin simular una clasificación. BrandDTO: id,name,productCount. Los IDs de relaciones publicadas no son autorización: deben validarse en cada consulta.

Filtros: OR dentro de marcas/categorías y AND entre grupos; rangos inclusivos min<=max, nulls al final y UUID como desempate. Facets se calculan sobre todo el conjunto público filtrado, no la página actual; al contar cada grupo se excluye el propio grupo para permitir selección múltiple. Búsqueda limitada a campos públicos; parametrizada, acotada y con límites de paginación. El servicio Next deberá enviar arrays como parámetros repetidos y mapear q/sort a search/ordering. No filtrar localmente una página parcial.

Errores: 400 filtros/documento inválido; 401/403 administración sin sesión/permiso; 404 hostname o producto no elegible; 412 precondición comercial obsoleta; 429 límite; 503 temporal. El error público no explica a qué empresa pertenece un UUID ajeno. Rate limit y su infraestructura deben definirse antes de publicar estos endpoints.

## CMS, Home y destacados

La Home mantiene la plantilla ecommerce y sus componentes StoreHeader/StoreHero/AnnouncementSlider/StoreHome/StoreFooter. No existe `src/templates/` en el checkout actual; no crear un segundo sistema de plantillas para cumplir una ruta referencial.

La selección specials del documento publicado controla únicamente IDs/orden editorial; se resuelve contra productos comercialmente elegibles y valores vivos. WebsiteProduct.is_featured/position puede alimentar la sección general de destacados comerciales. Definir una fuente por sección y no mezclar silenciosamente las dos selecciones. Despublicar comercialmente un producto lo retira de ambas proyecciones sin editar el snapshot CMS histórico.

Reutilizar ProductCard, StoreCatalog, filtros y paneles actuales, con búsqueda/paginación/facets de servidor. Revisar estados vacíos/error/carga, imágenes reales, focus y móvil/tablet/escritorio cuando se habilite el navegador. Las referencias Promart/Sodimac/Falabella son direcciones visuales futuras; en esta auditoría no se copiaron ni incorporaron código o activos de terceros, ni se rediseñó el sitio.

commerceEnabled debe ser una capacidad calculada desde una política comercial válida y una activación explícita de la funcionalidad, independiente de publicar un banner. Hoy es false en P1 y está forzado a false en store.js; se conserva. Antes de modificarlo, acordar su configuración persistente/feature flag y criterios. La existencia de WebsiteProduct o de stock no lo activa automáticamente.

## Carrito y administración por dominio

El carrito existente persiste id/cantidad/notas por storeId (máximo200 líneas, cantidades enteras1–999, moneda de UI PEN). B4-D necesita Website UUID estable, unitId, límites comunicados (propuesta50 líneas), resolución de IDs por servidor y conservación de selecciones que no están en la página cargada. No truncar ni borrar un carrito silenciosamente al pasar a paginación o cambiar límites. No persistir precios como autoridad.

La respuesta de cotización debe incluir moneda/importes recalculados, estado por línea y expiración; WhatsApp usa exclusivamente el teléfono del contacto publicado del mismo Website y líneas validadas. Enviar texto sigue siendo acción del usuario. No crear documentos fiscales, ventas, stock reservado ni cotizaciones ERP. El servicio de cotización es comercial y no una publicación CMS.

Actualmente `/admin` Next muestra administración Website/catálogos; AuthGuard cliente redirige a `/login` sin sesión/empresa. `src/lib/admin/routes.mjs` mantiene los módulos ERP como vistas de transición a Django. Convertirlo en un ERP Next completo es un alcance independiente, no un efecto de integrar catálogo.

También hay una colisión de rutas objetivo: `/catalog` hoy sirve el catálogo laboral. Mantener `/shop` y `/shop/[id]` para e-commerce hasta aprobar una migración de URLs/consumidores. Los Route Groups actuales se conservan. La propuesta empresa.com/catalog no autoriza sustituir esa ruta laboral en B4-A.

Los tokens administrativos actuales viven por origen del navegador; no se transportan automáticamente entre dominios. No copiarlos por query, cookies amplias, postMessage entre empresas o redirecciones libres. B5 deberá definir si se inicia sesión por cada dominio o se usa un intercambio seguro, restringido y de corta duración desde una administración central. Revalidar siempre membresía/Company y correspondencia del dominio, incluyendo dominios pendientes/inactivos y cambio de empresa. No implementar otro login.

## Orden de trabajo y aceptación futura

La numeración de la solicitud actual prevalece: B3-A validación; B4-A auditoría; B4-B API; B4-C frontend; B4-D carrito/WhatsApp; B5 administración por dominio. Los documentos anteriores llamaban B5 al carrito; eso es contexto histórico, no una autorización para mezclar etapas.

1. Cerrar B3-A con dominio activado por su operador, navegador y medios autorizados. Mientras tanto solo diseño/auditoría.
2. Resolver remediación compatible P0 del catálogo heredado y aprobar política de precios/lista/unidades/almacenes, jerarquía y activación comercial. No cambiar esquema ERP sin justificar la necesidad.
3. B4-B: selectores/serializers exclusivos públicos reutilizando ERP y WebsiteProduct, configuración y publicación comercial con autorización/precondición, consultas optimizadas y tests PostgreSQL.
4. B4-C: conectar transportes Next al hostname/DTO acordado; pruebas HTTP y visuales de Home, filtros, detalle y metadata por tenant. Mantener el diseño y las rutas laborales.
5. B4-D: cotización recalculada y carrito por Website/unidad; pruebas de precios modificados, productos retirados, unidad ajena, moneda y WhatsApp de la empresa correcta.
6. B5: arquitectura de administración por dominio y transición ERP separadas, con contrato de autenticación revisado.

Matriz mínima B4: A no lee producto/lista/unidad/media/almacén de B; dominio desconocido/inactivo404; producto retirado desaparece de detalle/listado/facets/destacados; precio y stock ERP cambian sin E3; guardar banner no cambia publicación; publicación de banner no altera precios; lista ausente no revela fallback; precios finales correctos con/sin impuesto y conversiones; filtros/paginación globales y conteos coherentes; ausencia de campos privados en JSON/HTML/RSC; retiro inmediato/caché; carrito tras cambio de dominio/unidad; catálogos laborales/login intactos.

## Entrega realizada

Solo documentación/evidencias de B3-A y B4-A, más actualización del registro de continuidad frontend. No hay funcionalidades comerciales implementadas, código funcional modificado, migraciones, datos reales alterados, cambios DNS/R2, commits, pushes o despliegues. Los bloqueos B3-A permanecen explícitos; no se declara B4-B autorizado por superar tests unitarios.
