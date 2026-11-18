# Entrega B4-B: APIs comerciales y arquitectura de cuentas

17/11/2026. Backend `websites_backend@e3f479f`, frontend `mvp_website@856b711`; ambos limpios al iniciar. Se trabajó sobre esas ramas reales, sin checkout, merge, commit, push o despliegue. No se modificaron credenciales, `.env`, datos habituales ni maestros ERP.

## Resultado y alcance

K0–K7 están implementados con contratos separados del catálogo laboral. La lectura pública utiliza dominio activo/verificado, Website publicado con revisión válida, vínculos explícitos y política autorizada. El catálogo calcula precios, unidades y disponibilidad desde ERP vivo; cambiar un precio/stock no requiere publicar el CMS.

**commerceEnabled sigue false.** Ni las publicaciones, la configuración o la existencia de productos activan la tienda. No se conectó Next a K0–K7, no se implementó B4-C, registro comercial, carrito o WhatsApp.

Las decisiones y la aprobación del usuario constan en [19](19-decisiones-b4-b.md). La auditoría/diseño de identidad, vínculo User–Customer–Company, dashboard y solicitudes WhatsApp está en [20](20-arquitectura-cuentas-comerciales.md); no contiene funcionalidades de registro implementadas.

## Archivos

Nuevos de dominio:

- `apps/websites/catalog/__init__.py`
- `apps/websites/catalog/permissions.py`
- `apps/websites/catalog/selectors.py`
- `apps/websites/catalog/projection.py`
- `apps/websites/catalog/services.py`
- `apps/websites/catalog/signals.py`

Nuevos de API/pruebas: `apps/api/v1/website_catalog/{__init__,serializers,views,urls}.py` y `apps/websites/tests/test_catalog.py`.

Modificados: `apps/api/v1/urls.py` añade el include independiente; `apps/websites/apps.py` registra la limpieza comercial segura; `apps/websites/tests/test_api.py` actualiza una expectativa antigua sobre ausencia de rutas comerciales.

No se cambiaron modelos, migraciones, lógica de ventas/compras/inventario, login/refresh o permisos laborales. Frontend: únicamente notas documentales de continuidad; no B4-C ni cambios visuales.

## Contratos implementados

Base `/api/v1/`, UUID y trailing slash:

| Contrato | Método/ruta | Regla |
| --- | --- | --- |
| K0 | GET `storefront/sites/{hostname}/products/` | Página, búsqueda, filtros, orden y facets públicos |
| K1 | GET `storefront/sites/{hostname}/products/{productId}/` | Detalle y unidades comerciales del Product publicado |
| K2 | GET `storefront/sites/{hostname}/categories/` | Categorías con productos elegibles; parent_id=null |
| K3 | GET `storefront/sites/{hostname}/brands/` | Marcas con productos elegibles |
| K4 | GET `websites/{websiteId}/catalog-product-options/` | manage.website; opciones propias sin precios/costos/proveedores |
| K5 | GET/PATCH `websites/{websiteId}/catalog-settings/` | Lectura autorizada; escritura de política solo ADMIN de empresa/superusuario |
| K6 | GET/POST `websites/{websiteId}/products/` | Consultar/crear WebsiteProduct; no duplicar Product |
| K7 | PATCH/DELETE `websites/{websiteId}/products/{publicationId}/` | Editar/retirar vínculo; nunca elimina el maestro Product |

K0 acepta `search`, `category`/`brand` repetibles (OR en el grupo, AND entre grupos), `min`, `max`, `featured`, `ordering`, `limit`, `offset`. Facets excluyen su propio grupo al contar alternativas, antes de paginar. Ordenaciones: name, name-desc, price-asc, price-desc, featured; precio nulo al final y UUID como desempate. discount se rechaza. Filtros numéricos/UUID inválidos y parámetros no permitidos devuelven400; no amplían la consulta.

Reconciliación de página predeterminada: `productsPerPage` del Website se utiliza cuando K0 no recibe limit; sin configuración,24. Limit explícito1–100; configuración1–60. K2/K3 predeterminan100. Offset0–2147483647. Las respuestas paginadas incluyen websiteId/count/limit/offset/results; K0 añade facets. No se usó el contrato histórico `stores/{id}` preparado en Next: adaptarlo corresponde a B4-C.

Se conservan los DTO públicos de16, allowlist dedicada, imágenes desde Product y unidades válidas. K1 añade SEO aprobado y saleUnits. Los campos privados no están presentes: costos/compra, proveedores, listas, almacenes/ubicaciones/cantidades exactas, márgenes, Company fiscal o datos de clientes.

Ajuste de DTO autorizado respecto a16: K5 no entrega IDs/opciones de listas ni almacenes a roles CMS sin administración comercial; devuelve canManagePolicy=false y los campos de presentación no sensibles. K6/K7 omiten priceListId a esos lectores. La ausencia no equivale a que la configuración esté vacía. Para ADMIN/superusuario se mantienen IDs seleccionados y opciones activas propias, sin importes o cantidades.

## Precio, unidad y disponibilidad

Lista elegida: override explícito en WebsiteProduct, si existe; en otro caso defaultPriceList de configuración. La lista debe estar activa y pertenecer a la Company. Solo se usa ProductPrice activo, no negativo y en la moneda del Website. Un override inválido o sin precio produce null; no vuelve a la lista predeterminada ni a price_sale, price_purchase o precios de ProductUnit. Un cero autorizado permanece0.00.

El precio mostrado corresponde a la unidad de venta predeterminada activa/válida; si no existe, a la base. Precio base de lista × factor; impuestos añadidos solo si la lista no los incluye y la afectación corresponde. Se usa la tasa vigente de `tax_rate_for_company` y redondeo monetario final equivalente al ERP; sin conversión cambiaria implícita. Todas las ordenaciones y filtros usan ese mismo precio SQL, no otro precio interno. K1 aplica la misma política a sus unidades.

Disponibilidad: suma neta de almacenes explícitos, activos, de Store activa y Company correcta. Sin almacenes válidos/configuración, unknown. Servicios sin control de inventario también unknown. Se compara el saldo con el factor de la unidad ofrecida; no se reserva ni modifica stock. showOutOfStock=false oculta unavailable, no unknown.

Caso de seguridad adicional: PriceList usa FK SET_NULL en los modelos históricos. Eliminar una lista override habría permitido heredar silenciosamente otra lista. El nuevo pre_delete retira las publicaciones activas afectadas bajo bloqueo de Website y audita la retirada, antes de la limpieza FK. No impide eliminar la lista ERP, no cambia precios/stock ni activa publicaciones. La retirada también se probó concurrentemente con una edición comercial. Borrar la lista predeterminada deja sin precio a quienes dependían de ella; no hay fallback interno.

## Seguridad, concurrencia y activación

JWT existente; usuario/Company/Store activos, membresía vigente, ownership y permisos actuales. No se autoriza por claims antiguos, company_id público o capacidades inferidas únicamente de medios/dominios. Los permisos CMS no conceden costos ni administración de listas/almacenes. Se conserva P0: miembros sin rol/SELLER/CASHIER leen el catálogo laboral básico; privado solo ADMIN de Company/superusuario.

Crear/editar vínculo no publicado requiere manage.website. Publicar, retirar, eliminar o editar una publicación activa exige además publish.website. K5 PATCH y cualquier priceListId en K6/K7 requieren administración de Company. Campos desconocidos/precios/stock/identificadores de maestro se rechazan. GET no crea configuración ni Website.

K5/K6 GET y escritores leen/bloquean el agregado Website para devolver representación y ETag coherentes. If-Match es un ETag fuerte `"catalog-<sha256>"` de settings, M2M y publicaciones. No incluye el contador editorial ni precios/stock ERP. Sin precondición428; obsoleta412; ETag editorial o formato inválido400. Se conserva el trabajo del cliente: el servidor no reintenta sobrescribiendo otro cambio.

Todo escritor usa servicios transaccionales y AuditLog con actor/fecha/cambios. No cambia editorial_revision. Django Admin sigue siendo de inspección y no evita estos servicios. Las respuestas llevan no-store; las administrativas varían por Authorization. No se añadió un contador comercial ni una migración: la huella medida es suficiente para este volumen; reevaluar ante mayor escala.

Fuente de activación recomendada: **un único opt-in persistido en WebsiteCatalogSettings**, defaultFalse, auditado, en una futura migración aditiva revisada. No añadir simultáneamente un feature flag por Website como otra autoridad. En esta entrega no se crea el campo ni un mecanismo de activación; ambos contratos de contexto/configuración mantienen el comercio deshabilitado.

Antes de activar: aceptar B4-B y conectar/probar B4-C; confirmar listas/moneda/impuestos/unidades y almacenes; catálogo publicado revisado; dominio verificado; medios/CDN reales; permisos/aislamiento; límites operativos, caché y pruebas visuales. La API K0–K3 ya permite consultar publicaciones expresamente autorizadas para verificar el backend, pero no habilita la tienda Next ni pedidos.

## PostgreSQL y validaciones

Configuración real: Django5.2.19, DRF3.18.3, psycopg3.3.8, PostgreSQL18.1. La inspección READ ONLY de `apudig_mvp` local encontró14 tablas Website y ningún nodo pendiente; historial/grafo y restricciones se guardan en [b4-database-audit.json](b4-database-audit.json). No se aplicaron migraciones ni se escribieron fixtures allí.

Pruebas ejecutadas exclusivamente en `test_apudig_catalog_p0_tests`, creada/destruida por Django con maestros A/B sintéticos. Modelos y todas las migraciones existentes se prueban al construir esa base; no se ejecuta migración productiva. `manage.py check` sin problemas; `makemigrations --check --dry-run` sin cambios.

La evidencia de [regresión](b4-regresion.json) separa baseline y versión actual. La suite ERP global **no está aprobada**: mantiene los mismos casos fallidos del baseline, sin casos nuevos fallidos. La matriz comercial incluye aislamiento, host desconocido/inactivo/no verificado, publicaciones activas/retiradas, Product inactivo, precios ausentes/negativos/moneda ajena, impuestos, unidades, almacenes ajenos/inactivos, saldo neto, facets/filtros/paginación, ETags, publicación/configuración concurrente, altas duplicadas y pérdida de override. También conserva la regresión laboral/administración.

Resultados:186 pruebas acotadas correctas, incluidas28 pruebas comerciales nuevas. Baseline actual695 casos:79 fallos y36 errores. Versión final723 casos: exactamente esos79 fallos y36 errores, sin nuevos casos fallidos. Este baseline se volvió a ejecutar sobre e3f479f; no se reutilizó la cifra113 de entregas anteriores. Frontend:50 pruebas Node existentes correctas; no se repitieron lint/build porque no se modificó código frontend ni se implementó B4-C.

El test de B1 que esperaba que las rutas comerciales no existieran fue actualizado a su nueva responsabilidad: descubrimiento solo lectura, configuración sin bootstrap ni política para el lector y dominio no publicado404. No se alteraron expectativas de fallos ERP para ocultar regresiones. Los fixtures concurrentes crean sus permisos y no dependen de semillas eliminadas por flush.

OpenAPI completo: [b4-openapi.json](b4-openapi.json); auditoría de las8 rutas, autenticación, allowlists y precondiciones: [b4-schema-audit.json](b4-schema-audit.json). Los contratos nuevos no generan errores/colisiones de esquema. La exportación global conserva97 advertencias y113 errores históricos de documentación ERP; no se declara validado todo el esquema.

## Rendimiento medido

[b4-performance.json](b4-performance.json) contiene EXPLAIN ANALYZE/BUFFERS y mediciones sintéticas en PostgreSQL18.1. Listado con2 y27 productos:14 consultas en ambos casos, sin N+1. Se ensayaron1.002 productos, página100, filtro de precio y ordenación; la evidencia conserva tiempo HTTP, planificación/ejecución SQL y coste de ETag. Son medidas locales, no un SLA ni una prueba de carga productiva.

La huella comercial cuesta O(n) en publicaciones y se calcula dentro del bloqueo; a escala mayor puede justificar un contador persistido. Las subconsultas acotan lista, unidad y stock sin multiplicar filas ni hacer consultas por producto. Categorías/facets y opciones administrativas cargan conjuntos de etiquetas/opciones: revisar paginación/rate limits y coste con el tamaño real antes de exposición productiva. No se añadieron índices/migraciones especulativos ni almacenamiento duplicado de precios/stock.

## Reproducción

Desde backend, secuencialmente, con el PostgreSQL local autorizado y permiso de crear bases de prueba:

```powershell
.\.venv\Scripts\python.exe docs\architecture\website-integration\run_catalog_security_checks.py --run-isolated . ..\.tools\b4-scoped.json apps.websites apps.inventory.tests.test_catalog_security apps.inventory.tests.test_catalog_api apps.users.tests.test_company_administration
.\.venv\Scripts\python.exe docs\architecture\website-integration\run_catalog_security_checks.py --run-isolated . ..\.tools\b4-all.json
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py spectacular --format openapi-json --file ..\.tools\b4-openapi.json
```

El runner fuerza la base desechable y devuelve error si hay fallos. El comando global seguirá devolviendo error mientras existan los fallos ERP documentados. Reutiliza únicamente las credenciales PostgreSQL locales configuradas para el servidor de integración y no las imprime. No usar la base habitual para provisionar A/B o probar publicaciones.

## Pendientes y límites

B4-C: adaptar el transporte Next preparado (`stores/{id}` histórico) a hostname/websiteId y los K0–K7 definitivos, aplicar capacidades y ETag comercial, conectar facets/paginación sin filtros parciales en memoria, probar responsive/navegación real. No implementar ni activar esa integración hasta revisar esta entrega.

R2/CDN real y revisión visual autenticada siguen pendientes desde B3-A; esta intervención no afirma validación de medios o navegador. Las pruebas son API/ORM/PostgreSQL sin mocks comerciales; no demuestran el storefront conectado. No se desplegó ni se habilitó comercio. Otras APIs ERP con contexto opcional y consumidores externos siguen requiriendo auditoría/coordinación independientes.

Cuentas/WhatsApp: revisar la propuesta20, aprobación y verificación por empresa, retención/privacidad, contexto JWT comercial, Customer existente, `/cuenta` frente a `/admin` y la solicitud persistida antes de implementar. No hay segundo login, cuentas comerciales funcionales, carrito, mensajes, SalesQuotation, ventas o reservas generadas por esta entrega.
