# Política comercial y contratos preparados para B4-B

Actualización 17/11/2026: la seguridad del catálogo laboral se implementó separadamente en [17](17-remediacion-p0-catalogos.md), tras aprobación del login obligatorio y del acceso privado de administradores de empresa. Esto no aprueba ni implementa la política comercial o los contratos K0–K7 de este documento. Commerce sigue deshabilitado.

Fecha: 16/11/2026. Propuesta técnica consolidada para revisión, **no contratos implementados**. Conserva rutas/nombres del informe14 y los distingue del parche P0 del informe15. Ningún cambio de precio/stock, vínculo comercial, flag, modelo o migración se ejecuta en esta entrega.

## Reglas comerciales de la propuesta

### Publicación y fuentes de verdad

WebsiteProduct es el vínculo entre Website y Product ERP; is_published controla elegibilidad comercial. No existe otro maestro público. Resolver Website con el hostname activo/verificado y exigir Website publicado, Company activa, Product.active y product.company_id igual a la Company del Website. Las relaciones con Company nula o cruzada no son publicaciones válidas.

La revisión CMS publicada conserva solo identidad/contacto/SEO, banners y selección/orden editorial. Los IDs de specials se resuelven en vivo contra WebsiteProduct elegible; retirar un vínculo lo oculta aunque siga citado en una revisión anterior. is_featured/position alimentan la sección comercial general de destacados, sin convertirse en otra copia mutable de specials.

Cambiar un precio, unidad, actividad o stock ERP se refleja en la siguiente petición comercial tras commit, sin E3 ni modificación de editorial_revision. Cambiar un banner sigue requiriendo E2/E3. K0–K3 y la eventual cotización no leen precios históricos del snapshot CMS.

### Precio autorizado

1. Lista elegida explícitamente en WebsiteProduct.price_list; si no existe override, WebsiteCatalogSettings.default_price_list. Ambas deben pertenecer a la Company y estar activas. Elegir una lista para exposición pública es una operación comercial autorizada, no se deduce de PriceList.is_default.
2. Override inválido/inactivo o sin fila de precio: price=null y señal de configuración administrativa; **no fallback silencioso** a otra lista o a la predeterminada. Sin override y default ausente/inválido: price=null. No listar todas las listas para que el navegador elija.
3. Solo ProductPrice activo del producto/lista seleccionada y moneda del Website. Moneda distinta o importe negativo: price=null; no conversión cambiaria implícita. Un importe explícito0 es válido, no equivale a ausencia.
4. Prohibidos como fallback: Product.price_purchase, costos, márgenes, ProductUnit.purchase_price, Product.price_sale y ProductUnit.sale_price. Estos últimos son precios de venta ERP, pero no están autorizados públicamente por el mero hecho de existir. No llamar resolve_commercial_price sin controlar su fallback y su precedencia de precio por unidad.
5. Si prices_include_tax=True, el importe de lista ya es final; no añadir impuesto otra vez. Si False, calcular precio final con tax_rate_for_company/gross_from_unit_value y tax_affectation del producto. Respetar fecha/vigencia y exoneraciones; no fijar IGV18 en JSX. La salida es precio final y priceIncludesTax=true.
6. Decimal durante cálculo; redondeo comercial canónico al final, string decimal en JSON. Toda operación debe usar la misma moneda/importe que filtros y ordenación. Frontend puede formatear el valor, no recalcular su autoridad.
7. original_price=null y promociones visuales no generan descuentos comerciales. El orden discount permanece inhabilitado hasta disponer de fuente autorizada de precio anterior.

Esto constituye la política inicial recomendada. Aprobar qué lista se podrá seleccionar y qué roles pueden publicarla antes de convertirla en código.

### Unidades comerciales

La unidad base es Product.unit. Una conversión es válida solo mediante ProductUnit activo del mismo Product, factor positivo y Unit asociado; Unit es global, por lo que su autorización proviene del producto/conversión, no de un company_id inexistente en Unit.

Propuesta: K0 muestra la unidad de venta por defecto activa si existe; de lo contrario la base. K1 puede exponer también las unidades de venta válidas. El precio de cada conversión se calcula como precio base de la lista autorizada × conversion_factor, con tratamiento de impuesto coherente y redondeo final. Se ignoran sale_price/purchase_price internos de ProductUnit como fuente pública. No aceptar un factor enviado por el navegador.

La selección de unidad y cantidades se valida de nuevo en la futura cotización. El primer contrato puede restringir cantidades a enteros1–999 por unidad; si el negocio requiere fracciones, acordar precisión y mínimos antes de implementarlos. No eliminar conversiones ERP ni sustituirlas por unidades ficticias.

### Disponibilidad

Solo los Warehouse seleccionados explícitamente en WebsiteCatalogSettings.warehouses, activos, con Store activa y de la Company. Una selección con almacenes ajenos se rechaza al escribir y se excluye defensivamente al leer. La M2M requiere validación en servicio: clean del modelo no basta para una escritura .set().

- Sin política o selección de almacenes: unknown, nunca sumar todos los almacenes.
- Product.tracks_inventory=False: unknown/consulta comercial, no agotado automático por inexistencia de stock.
- Con selección válida: sumar StockByWarehouse del producto en esos almacenes, conservar la semántica neta y limitar el saldo negativo a cero para disponibilidad. No convertir un negativo en inventario positivo sumando solo almacenes positivos.
- available significa que la lectura permite al menos una unidad comercial mostrada (saldo base >= factor de conversión); unavailable si no alcanza. No exponer cantidades exactas, almacenes, ubicaciones ni movimientos en DTO público.
- show_out_of_stock=False oculta unavailable, no unknown. La disponibilidad observada no reserva stock ni garantiza entrega; la futura cotización valida cantidad × factor de nuevo.

## Contexto, publicación y autorización

K0–K3 son anónimos y usan el selector público por hostname ya existente. Nunca aceptan company_id, store_id o price_list_id del navegador como contexto público. No usan BaseCompanyAPIView con contexto opcional ni los serializers del catálogo laboral. No envían/reciben cookies o JWT administrativos como requisito de lectura pública.

K4–K7 reutilizan JWT y la revalidación actual de Website: usuario activo, Company/sucursal activa, membresía vigente, propiedad del Website y relaciones del mismo tenant. La correspondencia de dominio administrativo y empresa sigue las restricciones existentes; administración entre dominios queda separada para B5.

| Acción administrativa | Permiso mínimo propuesto |
|---|---|
| Leer configuración/vínculos del Website | Lectura editorial efectiva, con membresía vigente; no incluye costos ni todas las listas ERP |
| K4 buscar opciones ERP para selección | manage.website, porque permite descubrir productos aún no publicados de la Company |
| Crear/editar vínculo no publicado | manage.website |
| Publicar/retirar vínculo o editar copy/precio/posición de un vínculo publicado | manage.website + publish.website |
| Cambiar configuración que afectará al público (lista/almacenes/disponibilidad) | manage.website + publish.website |
| Eliminar vínculo por K7 DELETE | manage.website + publish.website; nunca elimina Product |

K4 se restringe respecto a la lectura editorial genérica propuesta en14: el motivo es no ampliar lectura de productos ERP no publicados a un rol dedicado únicamente a medios/dominios. No cambia ningún endpoint existente porque K4 todavía no está implementado. Al implementar, evitar que view inferido de cualquier capacidad Website otorgue permisos comerciales más amplios de lo acordado.

WebsiteProduct no tiene un segundo borrador comercial para copy de un producto ya publicado. Una edición sobre un vínculo activo es una modificación pública directa autorizada; no presentar una UI que prometa guardar un borrador comercial separado inexistente. Si se exige ese flujo después, justificar su esquema sin duplicar el CMS.

## Caché y concurrencia

Lecturas públicas y administrativas no-store inicialmente. Así los cambios ERP aparecen en la siguiente petición autorizada. React cache solo por petición y Host; no compartir resultados entre dominios/usuarios. Con caché futura, definir invalidación on_commit de precio, unidad, stock y publicación, con clave Website/moneda/política/query; la revisión CMS no basta.

Escrituras K5–K7 bloquean Website, revalidan permisos/referencias y exigen If-Match **comercial**, separado del contador editorial. Responder428 sin precondición,412 si está obsoleta. Propuesta sin migración inicial: ETag opaco derivado del estado comercial canónico (settings y sus timestamps, IDs M2M ordenados, publicaciones/timestamps), comparado bajo el mismo bloqueo; no incluir precio/stock ERP, porque no son una edición de configuración. Todo escritor M2M debe actualizar su agregado mediante el servicio. Validar el costo de ese hash antes de elegirlo; un contador persistente solo se añadirá si la medición justifica una migración.

Auditar actor/fecha/cambios de política y publicación en la transacción. No emitir confirmaciones ni invalidaciones externas de éxito antes del commit. No permitir cambios por Django Admin de inspección que eludan estos servicios.

## Contratos técnicos propuestos

Base `/api/v1/`, trailing slash. Hostname normalizado sin esquema/puerto/path en el contrato público; unknown/inactivo/no publicado404 uniforme. Content-Type JSON, errores estructurados code/message/fields. Las formas siguientes no activan endpoints.

| ID | Método y ruta | Entrada | Salida |
|---|---|---|---|
| K0 | GET `/storefront/sites/{hostname}/products/` | search, category y brand repetibles, min/max, ordering, featured opcional, limit24/máx100, offset | websiteId,count,limit,offset,results:[ProductDTO],facets |
| K1 | GET `/storefront/sites/{hostname}/products/{productId}/` | Product UUID, sin company_id/lista elegida por cliente | websiteId,product:ProductDetailDTO; ajeno/inactivo/retirado404 |
| K2 | GET `/storefront/sites/{hostname}/categories/` | limit100/máx100,offset | websiteId,count,results:[CategoryDTO] |
| K3 | GET `/storefront/sites/{hostname}/brands/` | limit100/máx100,offset | websiteId,count,results:[BrandDTO] |
| K4 | GET `/websites/{websiteId}/catalog-product-options/` | search,limit24/máx100,offset; permisos de selección | websiteId,count,results:[{productId,name,sku,unitId,unit}] |
| K5 | GET/PATCH `/websites/{websiteId}/catalog-settings/` | PATCH defaultPriceListId|null, warehouseIds[], showOutOfStock, productsPerPage1–60, If-Match comercial | Configuración del Website + ETag; GET sin fila devuelve configuración vacía calculada, no crea registros |
| K6 | GET/POST `/websites/{websiteId}/products/` | GET búsqueda/paginación; POST productId, isPublished=false por defecto, isFeatured, position, priceListId|null y copy permitido; If-Match | Lista de PublicationDTO o201 vínculo nuevo;409 duplicado, sin duplicar Product |
| K7 | PATCH/DELETE `/websites/{websiteId}/products/{publicationId}/` | Campos comerciales permitidos/retirada y If-Match; publicationId es UUID de WebsiteProduct | PublicationDTO + ETag o204; ningún cambio del maestro ERP |

PATCH K5 crea la configuración inicial solo mediante escritura explícita autorizada si aún no existe; validates relaciones y publica la política de forma atómica. GET no crea WebsiteCatalogSettings. Moneda proviene del Website y no es un campo fiscal editable en este PATCH. Una operación inválida no debe guardar relaciones parciales.

Para poder configurar K5 sin inventar IDs, su GET puede incluir opciones administrativas de selección para quien tenga permisos de gestión/publicación: priceListOptions[{id,name,pricesIncludeTax}] y warehouseOptions[{id,name,storeId}]. Siempre activas y de la Company autorizada, sin importes, costos, cantidades o ubicaciones. No reutilizar un listado ERP global como selector. Estas opciones son una ampliación propuesta del DTO administrativo, no campos de la API pública ni datos disponibles para un rol exclusivamente de medios/dominios.

PublicationDTO: id (del vínculo), productId, slug, commercialTitle, commercialDescription, seoTitle, seoDescription, isPublished, isFeatured, position, priceListId, updatedAt. Campos de copy con límites actuales de modelo (180/1000/70/170). Campos desconocidos, precios/costos/stock y company_id enviados para modificar el maestro se rechazan. Slug único por Website, generado/normalizado por servidor; K1 conserva Product UUID según la ruta acordada.

ProductDTO: id (Product UUID), name, sku, description, brand:{id,name}|null, category:{id,name}|null, unitId, unit (etiqueta), currency, price:string|null, priceIncludesTax:true, original_price:null, image_url, image_alt, images[], availability y badge autorizado. ProductDetailDTO añade saleUnits:[{unitId,unit,price,availability}], únicamente opciones válidas de ese producto. No incluir factores internos si el cliente no los necesita; el servidor es autoridad de la conversión.

CategoryDTO: id,name,parent_id,productCount. BrandDTO: id,name,productCount. Actualmente Category es plana: parent_id=null. No inventar subcategorías. La jerarquía real requiere una propuesta separada de Category.parent y aprobación de cambios ERP, no una migración implícita de B4-B.

K0 filtra/ordena por la misma oferta comercial que devuelve: precio final de la unidad mostrada, nulos al final y UUID como desempate. min/max inclusivos con min<=max; invalidar formatos/monedas que no corresponden, no intercambiar valores silenciosamente en servidor. OR dentro de marcas/categorías, AND entre grupos; no consultar FK ajenas para explicar un error. Búsqueda por nombre/SKU públicos, sin supplier_codes/nombres de proveedor. Facets cuentan el conjunto elegible completo antes de paginar; cada grupo excluye su propio filtro al contar alternativas.

Selectores optimizados con select_related/prefetch/subqueries acotadas; no N+1 de impuestos, lista, unidades y stock. Resolver detalle y listas con la misma política; count/facets/categorías/marcas no pueden revelar productos retirados o de otra Company.

No exponer price_purchase, inventory_unit_cost, last_purchase_unit_value, purchase_price de conversiones, proveedores/supplier_codes, márgenes, todas las listas, stock_by_warehouse, ubicaciones o datos fiscales. Precio ausente significa null, nunca0 inventado. La UI conserva errores401/403/404/412/428/429/503 y no convierte una denegación en una lista demo.

## Activación y decisiones que deben quedar aprobadas

commerceEnabled continúa false. Debe existir un opt-in explícito por Website y comprobarse la preparación del código/política antes de activarlo. La existencia de un vínculo o de una lista configurada no lo activa sola.

Decisión pendiente: dónde persistir el opt-in. Un boolean commerce_enabled en WebsiteCatalogSettings, defaultFalse y auditado, sería la ampliación mínima si se necesita gestión permanente desde UI; requiere justificar/aprobar una migración aditiva antes de crearla. Alternativamente, un feature flag de despliegue por Website puede mantener la activación fuera del esquema durante el piloto. No añadir ambos como autoridades contradictorias. Esta entrega no elige ni implementa una activación productiva por inferencia.

Antes de B4-B: aprobar política de lista autorizada y roles, unidad mostrada/cantidades fraccionarias, reglas de disponibilidad y opt-in/ETag. La propuesta segura arriba sirve como baseline de implementación, pero no reemplaza la decisión de negocio. No iniciar B4-C/D ni cotizaciones/WhatsApp hasta preparar y probar el contrato correspondiente.

## Matriz de pruebas a implementar en la remediación y B4-B

Estas son pruebas de aceptación nuevas previstas; no se presentan como ejecutadas. El diagnóstico del15 demuestra los fallos actuales con fixtures separados.

| ID | Caso | Resultado exigido | Nivel |
|---|---|---|---|
| L01 | Listado/detalle legado sin token o sin empresa firmada |401/403 antes de cualquier consulta global | API PostgreSQL |
| L02 | JWT válido pero membresía revocada, Company o Store inactiva/ajena |403 y sin costos/productos | API |
| L03 | Usuario A solicita Product UUID B o company_id de formulario/query B |404 o denegación; nunca contenido B | API |
| L04 | Usuario básico vs usuario con permisos privados | Costos/listas/almacenes/proveedores solo con autorización explícita | API |
| L05 | `/catalog` y `/admin/catalog_admin`, login/refresh/cambio de empresa | Rutas/envelope conservados; contexto revalidado; errores visibles | HTTP + navegador |
| L06 | Abrir modal privado, cambiar empresa/usuario/modo, abrir mismo ID | Sin datos cacheados del contexto anterior; cancelar respuestas antiguas | Navegador |
| L07 | Acceso alternativo `/api/v1/products/` y detalle | No permite eludir el aislamiento del catálogo | API |
| P01 | Host desconocido/PENDING/DISABLED, Website no publicado o Company inactiva |404 uniforme, sin fallback | API + Next |
| P02 | A/B con mismos nombres/SKU y precios distintos | Cada Host muestra únicamente su contenido/metadata/precios | PostgreSQL + HTTP |
| P03 | Product activo pero sin WebsiteProduct publicado | No aparece en K0/K1/K2/K3/facets/destacados | API |
| P04 | Retirar producto referenciado por snapshot CMS | Se oculta sin E3 ni modificación de historial | API + HTTP |
| R01 | Default list válida y override válido | Solo precio de la lista elegida, misma Company/moneda | API |
| R02 | Lista/fila ausente, inactiva, ajena o de otra moneda; precio interno disponible | price=null, nunca fallback interno | API |
| R03 | Precio0 y precio negativo |0 explícito válido; negativo no se publica | Unit/API |
| R04 | prices_include_tax True/False, exoneración y tasa vigente de Company | Precio final correcto, sin impuesto duplicado | Unit/PostgreSQL |
| R05 | Cambiar ProductPrice ERP tras commit | Próxima petición refleja importe nuevo sin publicar CMS | HTTP/PostgreSQL |
| U01 | Unidad base/default venta, conversiones activas y factor positivo | Precio desde lista × factor, misma oferta en listado y detalle | API |
| U02 | Unit/ProductUnit de otro producto, conversión inactiva o factor cliente | Denegación sin seguir precios/costos internos | API |
| S01 | Sin configuración de almacenes | availability=unknown, no stock global | API |
| S02 | Almacén ajeno/inactivo o Store inactiva | Rechazo al escribir/exclusión defensiva al leer | API |
| S03 | Saldo negativo, pack mayor que saldo, servicio sin inventario | Disponibilidad conforme a política, sin cantidad exacta pública | Unit/API |
| S04 | Cambiar stock y showOutOfStock | Siguiente lectura coherente sin E3 ni reserva | API |
| F01 | Paginación, límites inválidos, empate de orden y precio null | Count/facets globales y orden estable antes de paginar | API |
| F02 | Multi marca/categoría, búsqueda y rango de precio | OR/AND coherentes; sin filtrar una página parcial en JSX | API + frontend |
| F03 | Categoría/marca ajena y relaciones Company null | No amplían conjunto ni revelan datos de otro tenant | API |
| D01 | Inspeccionar JSON y HTML/RSC públicos | Allowlist sin costos, proveedores, listas o almacenes | Contrato/HTTP |
| C01 | Mutaciones K5–K7 concurrentes, sin If-Match/obsoleto |428/412, rollback íntegro y ETag comercial independiente | PostgreSQL threads |
| C02 | Configuración/publicación por editor sin permiso publish |403 sin modificación pública | API |
| C03 | GET configuración inexistente | Respuesta calculada, sin escritura | API |
| C04 | Actualizar precio ERP mientras se edita un banner | Precio vivo y snapshot CMS consistentes con sus propias fuentes | PostgreSQL/HTTP |
| M01 | Imágenes de Product y Website de A/B, claves antiguas y URL inválida | Recursos propios/autorizados, sin mover claves históricas | API + R2 autorizado |

## Lista exacta de cambios futuros

### Parche P0 independiente (primero)

- `apps/api/v1/catalog/views.py`: contexto privado obligatorio, membresía activa y permisos por operación; sin cambio de rutas.
- Nuevo resolvedor estricto de contexto en un módulo de seguridad API, reutilizando JWT/user_can_access_context y membresía vigente. No activar el fallback permisivo cuando falte un módulo de permisos.
- `apps/api/v1/catalog/serializers.py`: separar proyección laboral básica y privada; allowlist y campos autorizados.
- `apps/api/v1/catalog/selectors.py` nuevo, o wrapper equivalente: nunca consultar catálogo con Company=None; filtrar relaciones secundarias.
- `apps/api/v1/inventory/views.py` y serializers/consumidores de `/products/`: corregir bypass de lectura con alcance de seguridad revisado, sin cambiar inventario operativo.
- `src/app/(catalog)/catalog/page.js` y su protección de acceso: si se aprueba login laboral, reutilizar AuthGuard/selección existentes.
- `src/components/catalog/CatalogPage.jsx`, `src/components/admin/ProductDetailModal.jsx`: limpieza por tenant/modo/usuario, manejo de401/403/loading y cancelación de peticiones; caché privada aislada o eliminada.
- `src/services/productsService.js` y tests: mantener rutas/envelope para clientes autorizados y errores estructurados; cualquier migración de anonimato se comunica.
- Pruebas catalog_api, administración/login y navegador según L01–L07; confirmar consumidores externos antes del corte.

### B4-B, solo después de revisión/aceptación

- `apps/websites/catalog_selectors.py`: selección por hostname, vínculos publicados y política ERP autorizada.
- `apps/websites/catalog_services.py`: mutaciones comerciales bajo bloqueo, ownership de FK/M2M, auditoría y precondición comercial; sin escribir maestros ERP.
- `apps/api/v1/websites/serializers.py`, `views.py`, `urls.py`: K0–K7 y OpenAPI público/administrativo separados de los serializers heredados.
- Nuevas pruebas de catálogo Website con precios/unidades/stock A/B y concurrencia PostgreSQL; fixtures solo de integración.
- Modelos/migración únicamente si se aprueba la necesidad del opt-in persistente o un contador comercial medido; no son cambios automáticos de esta lista. Category.parent requiere otra justificación/aceptación específica.
- Adaptar los transportes preparados Next a `/storefront/sites/{hostname}/...`, websiteId y paginación/facets acordadas en una entrega posterior de cliente; conexión visual/activación quedan para B4-C, carrito/WhatsApp para B4-D.

Cambios realizados **ahora**: únicamente informes15/16, evidencias HTTP y diagnóstico aislado reproducible, y notas de continuidad documental. No se ejecutó ninguno de los cambios funcionales futuros de esta lista.
