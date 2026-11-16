# 10 — Entrega B2: CMS, borradores, revisiones, publicación y medios

Fecha: 15/11/2026, America/Lima. Backend `apudig_mvp/develop`, HEAD base `c8296b7`, conservando el trabajo no confirmado de B1. Frontend `ad_frontend/mvp_website`, `57c212a`, sin modificaciones.

## Resultado

B2 implementa exclusivamente el backend editorial: documento v3, borrador persistente, revisiones inmutables, ETag global, publicación transaccional, restauración, preview autenticado e imágenes gestionadas. No se implementaron conexión Next, API pública de contenido, catálogo comercial, carrito, pagos, scheduler ni despliegues.

**92 pruebas Website correctas en PostgreSQL 18.1**, incluidas las 48 de B1 y 44 adicionales. Se ejecutó también la suite completa: **659 pruebas, 539 correctas, 84 fallos y 36 errores heredados**. El baseline B1 preservado antes de B2 ejecuta 615 pruebas con los mismos 84 fallos y 36 errores; no hay casos fallidos adicionales en la comparación. Ver [evidencia diferencial](b2-regresion.json).

La suite global sigue roja y no se declara aceptada como totalmente correcta. La comprobación del banner en dos navegadores permanece en B3; no se presenta como resultado de B2.

## Preservación y entorno

- Se verificaron develop y mvp_website. No hubo checkout, merge, rebase, cherry-pick, commit o push.
- Se preservó un snapshot de las 408 fuentes Python de B1 antes de editar. Sus hashes están en [manifest del baseline](b2-baseline-manifest.json); su digest queda registrado en la evidencia diferencial.
- `.gitignore` previo conserva el hash Git `3b726931da3d79b084bc803c3b5fae7d3039e612`. `.env` no se modificó ni se copió a los artefactos.
- No se modificaron fuentes de usuarios/auth, productos, inventario, ventas, POS, tesorería o reportes respecto a B1. Se reutiliza el procesador de imágenes ERP sin editarlo.
- Python 3.12.1, Django 5.2.19, DRF 3.18.3, psycopg 3.3.8; sin actualización de dependencias.
- PostgreSQL 18.1 en una instancia temporal separada, escuchando exclusivamente en loopback. Bases sintéticas `apudig_cms_integration` y `apudig_cms_baseline`, con bases de test independientes. No se usó ni migró la base habitual.
- La autenticación trust se limitó a la instancia local desechable con datos sintéticos; no es una configuración productiva. Al concluir las pruebas se detuvo PostgreSQL y se retiraron su directorio temporal, el snapshot de ejecución y los archivos auxiliares; los artefactos de evidencia se conservaron en esta documentación.

## Archivos creados y modificados

| Archivos nuevos | Responsabilidad |
|---|---|
| `apps/websites/documents.py` | Contrato v3, defaults informativos sin productos demo, validación y adaptación explícita de documentos v1/v2 |
| `apps/websites/editorial_adapter.py` | Conversión reversible documento ↔ Settings/Home/Sections |
| `apps/websites/errors.py` | Errores de dominio con código, status y rutas de campo |
| `apps/websites/services.py` | Guardar, leer, publicar, restaurar y construir revisiones completas bajo bloqueo Website |
| `apps/websites/media_storage.py` | Procesamiento, R2, deduplicación, limpieza de uploads fallidos y desactivación autorizada |
| `apps/api/v1/websites/parsers.py` | JSON acotado a 256 KiB y lectura multipart limitada; rechazo de JSON excesivamente profundo |
| `apps/api/v1/websites/schema.py` | Esquema Bearer del autenticador Website para OpenAPI; no altera autenticación |
| `apps/websites/migrations/0008_editorial_documents_revisions_and_media.py` | Extensión incremental del esquema editorial y referencias de medios |
| `apps/websites/tests/test_editorial.py` | Contratos, persistencia, permisos, publicación, restauración, errores, preview y CORS |
| `apps/websites/tests/test_media.py` | Imágenes reales procesadas con Pillow y almacenamiento R2 simulado |
| `apps/websites/tests/test_editorial_concurrency.py` | Carreras PostgreSQL entre editores, guardar/publicar y uploads duplicados |
| `apps/websites/tests/fixtures/editorial-v3.json` | Fixture generado desde createWebsiteDocument/validateWebsite reales del frontend, sin productos seleccionados |

Modificados: `apps/websites/{apps,blocks,models,permissions}.py`, `apps/api/v1/websites/{views,serializers,urls}.py`, `apps/websites/tests/{test_api,test_migrations}.py` y `config/settings.py`. Este último añade únicamente CORS para If-Match/ETag respecto a B1. Las expectativas de pruebas B1 se adaptan a que ya existe publicación backend y nuevos endpoints editoriales.

Documentación/evidencia: este informe, [OpenAPI Website](b2-openapi.json), [SQL revisado](b2-migration.sql), [comparación de regresiones](b2-regresion.json), manifest y notas de estado en 05/07/08. Los registros completos de pruebas son temporales; el JSON conserva identificación de los casos fallidos, conteos y diferencias sin volcar HTML de tests ni secretos.

## Documento y persistencia

El contrato deriva de `ad_frontend/src/lib/website/content.mjs`. Se validan las propiedades identity, contact, seo, heroSlider, banners, announcements, specials, promotions y sections, con límites y tipos estrictos. Se rechazan claves desconocidas, HTML, enlaces inseguros, periodos inválidos, IDs duplicados, data URLs y payloads excesivos.

Campos opcionales antiguos reciben defaults compatibles: heroSlider true/6000 y contacto adicional vacío. Los campos opcionales de avisos y el orden/IDs de elementos se conservan. `schemaVersion=3` del documento, schema1 de bloques y versión de plantilla ecommerce son conceptos distintos.

| Parte | Fuente mutable única |
|---|---|
| Identidad y contacto | WebsiteSettings; nuevos short_name, location, announcement, secondary_phone y hours_text |
| SEO | Home WebsitePage; los defaults históricos de Settings solo se usan si aún no hay SEO de Home |
| Banners/slider | WebsiteSection `hero_slider.v1` |
| Avisos/especiales/promociones | Bloques tipados `announcements.v1`, `specials.v1`, `promotions.v1` |
| Orden, título y visibilidad | WebsiteSection y bloques editoriales tipados para las siete secciones v3 |
| Referencias de imágenes del borrador | WebsiteDraftMedia, por campo estable basado en ID editorial |

No se añadió un JSON mutable con una segunda copia del borrador. Las copias completas se guardan únicamente como revisiones históricas inmutables. Guardar conserva secciones y banners ocultos; cambiar nombre/contacto web no escribe Company o CompanyBranding.

GET editor no crea Website, Settings ni páginas. Una web nueva recibe un documento inicial calculado; su primera persistencia requiere PUT autorizado. Los defaults no incluyen avisos/productos seleccionados ficticios. Los IDs comerciales no vacíos deben ser UUID canónicos de productos activos publicados en el mismo Website; no se crean productos, listas o cotizaciones.

El adaptador de importación v1/v2 es explícito, no una importación automática de localStorage. Conserva contenido y destinos, adaptando /catalog → /shop solo para documentos v1. Para documentos de etapas anteriores no se inventan productos ni avisos demo. HTTP exige schema v3.

## Revisiones, concurrencia y publicación

WebsitePageRevision se reutiliza con operation SAVE/PUBLISH/RESTORE/BASELINE, editorial_revision y source_revision. Cada snapshot nuevo contiene documento íntegro, schemaVersion, templateKey, templateSchemaVersion y mediaReferences. Se registran actor, fecha y versión propia de página, independiente del contador global.

- Guardar/publicar/restaurar usan transaction.atomic y select_for_update sobre Website antes de tocar hijos; vuelven a comprobar permisos actuales bajo el bloqueo.
- Cada operación exitosa incrementa editorial_revision una vez. If-Match usa la revisión global de todo el agregado.
- Guardar reemplaza únicamente el borrador y registra SAVE. No cambia published_revision ni published_at.
- Publicar requiere borrador guardado, lo valida de nuevo y crea un snapshot completo antes de mover el pointer. La página y Website se actualizan en la misma transacción.
- Un fallo después de actualizar el pointer revierte pointer, contador, snapshot y evento. No hay webhook o efecto externo de publicación en B2.
- Restaurar verifica pertenencia, medios y productos, crea un nuevo borrador/RESTORE y conserva la publicación vigente.
- Publicar no activa dominios ni verifica DNS. Un Website SUSPENDED no se reactiva por publicar.
- Las revisiones no admiten update/delete/bulk_update por el manager público ni eliminación por instancia; las páginas con revisiones y los medios referenciados tienen protección referencial. No hay CRUD heredado que evada el contador.

Los snapshots completos conservan contenido oculto para restauración. B3 deberá proyectar únicamente campos publicados/visibles desde ese snapshot, sin leer WebsiteSettings mutable. B2 no expone un endpoint público de contenido.

## Endpoints

Base `/api/v1/`, trailing slash. Todos requieren JWT existente, usuario activo, membresía actual y pertenencia del Website a Company. No se usa company_id de formulario, Host o X-Forwarded-Host como autorización.

| Contrato | Método / ruta | Permiso / respuesta |
|---|---|---|
| E0 conservado | GET `/websites/current/` | Descubrimiento propio y capacidades; realPublication ahora true porque el servicio backend existe |
| E1 | GET `/websites/{id}/editor/` | Lectura editorial; EditorRecord + ETag |
| E2 | PUT `/websites/{id}/draft/` | manage.website; `{document,mediaReferences?}`; EditorRecord + ETag |
| E3 | POST `/websites/{id}/publish/` | publish.website; sin documento en body; EditorRecord + ETag |
| E4 | GET `/websites/{id}/revisions/` | Lectura editorial; `{count,results}`, actor y fuente de restauración |
| E5 | POST `/websites/{id}/restore/` | manage.website; `{revisionId}`; EditorRecord + ETag |
| E6 | GET `/websites/{id}/preview/` | Lectura editorial; `{websiteId,revision,content}` del draft; ETag y noindex/nofollow |
| M0 | GET `/websites/{id}/media/` | Lectura editorial; `{count,results}` propios |
| M1 | POST `/websites/{id}/media/` | manage.website.media; multipart file/kind/altText; 201 nuevo o200 deduplicado |
| M2 | DELETE `/websites/{id}/media/{mediaId}/` | manage.website.media; 204 soft-delete o409 si está referenciado |

Nueve rutas Website en total, ocho añadidas a B1 porque M0/M1 comparten ruta. Las rutas comerciales antiguas no se montaron. E4/M0: limit20 por defecto, máximo100, offset>=0, validación de parámetros y orden estable.

Escrituras E2/E3/E5 exigen ETag fuerte como `If-Match: "4"`. Falta: 428; obsoleto: 412; formato/documento inválido: 400; sin permiso: 403; recurso ajeno/inexistente: 404. Una revisión de B no se puede restaurar en A. El publicador sin edición puede publicar el borrador guardado, pero no cambiarlo.

Errores `{code,message,fields?}` con rutas compatibles con la UI, por ejemplo banners.0.title o promotions.0.productIds. Respuestas privadas con Cache-Control private/no-store, también en errores. Preview siempre requiere autorización; parámetros draft/source no habilitan acceso anónimo. CORS permite If-Match y expone ETag sin cambiar orígenes ni credenciales.

EditorRecord conserva `{schemaVersion,companyId,websiteId,revision,draft,published,updatedAt,publishedAt,events,capabilities}`. events resume las últimas20 revisiones; historial completo paginado en E4. Capacidades derivan de grants reales, no de claims antiguos. realPublication indica disponibilidad backend; no implica que Next o el dominio público ya estén conectados.

El [OpenAPI adjunto](b2-openapi.json) documenta los nueve recursos, DTOs, Bearer, If-Match y ETag. No modifica el cliente Next preparado: B3 deberá descubrir el UUID con E0, inyectar el transporte y preservar errores estructurados.

## Imágenes

Se reutilizan inspect_product_image y optimize_product_image del ERP, así como su creación de cliente R2, sin cambiar productos ni sus claves.

- PNG/JPEG/WebP por contenido Pillow, extensión permitida, límites de tamaño, dimensiones y píxeles existentes; por defecto 5 MiB original.
- Optimización y thumbnail WebP, claves nuevas `websites/{websiteId}/media/{uuid}` y dimensiones del archivo procesado; no se guardan binarios en JSON.
- Se exige URL pública HTTPS de medios válida. No se importan URLs arbitrarias ni se hace fetch del servidor hacia ellas.
- El borrador admite URLs de medios activos del mismo Website o mediaReferences por ruta estable. El servidor deriva las URLs desde IDs autorizados; se rechazan medios ajenos, borrados y claves fuera del namespace gestionado.
- Referencias del draft y de cada revisión protegen el recurso. M2 solo desactiva si está libre; no elimina físicamente archivos que podrían seguir en URLs históricas.
- Borradores/bibliotecas históricas no conciliados se tratan de forma conservadora al eliminar medios: pueden exigir revisión manual antes de liberar un archivo.
- Checksum y bloqueo Website deduplican uploads idénticos, incluso concurrentes. Los roles de edición y gestión de medios se mantienen separados.
- Si falla R2 o el registro en BD, no hay éxito falso; se intenta limpiar únicamente claves nuevas de esa operación. La limpieza puede fallar durante una caída del proveedor y deja un registro operativo para conciliación de huérfanos.
- La subida usa una transacción durable propia para que un rollback externo inadvertido no deje un upload confirmado sin registro. No envolver este servicio en transacciones de aplicación adicionales.

**R2 real no se probó**: se usaron mocks controlados. Sí se procesaron imágenes reales con Pillow y se probaron ownership, límites, deduplicación, errores y rollback con PostgreSQL. Se conserva el modelo de URLs públicas CDN; las URLs no son autorización para reutilizar un medio desde otro Website.

## Migración y conciliación

0008 es la única migración nueva. Añade metadata de revisión, cinco campos de Settings, SEO180 en Home y tablas WebsiteDraftMedia/WebsiteRevisionMedia; protege páginas con historial. No reescribe snapshots históricos ni publica contenido automáticamente. Los registros antiguos reciben operation BASELINE y editorial_revision nullable.

Se verificó el baseline B1 en la instancia aislada antes de editar: 12 tablas Website compatibles con su historial. Después de revisar el plan y las operaciones se aplicó 0008 solo allí. Auditoría posterior: **14 tablas compatibles**; check, grafo, historial, makemigrations --check y migrate --check correctos.

Las migraciones 0001–0007 y users0006 se conservaron respecto al snapshot B1, incluidos los alias históricos de 0003/0004. No se usó --fake ni se borraron tablas para conciliar datos reales.

El comando estándar sqlmigrate encontró una referencia histórica intermedia de billing a sales.BusinessDocumentType al proyectar únicamente las dependencias Website. Se revisó el SQL con el estado completo de todos los nodos ERP aplicados, como en las pruebas de conciliación B1; se adjuntan [63 sentencias recopiladas sin ejecutarlas de nuevo](b2-migration.sql). No se modificó el historial ERP para ocultar este problema de proyección.

Las pruebas de migración comprueban upgrade desde B1 conservando snapshots históricos byte-equivalentes en su JSON, sin pointer público nuevo; upgrade desde baseline ERP con maestros/operaciones y compatibilidad de nombres completos/parcialmente aplicados. La base habitual no se consultó ni migró.

El CMS histórico de bloques que no representa el documento v3 requiere conversión explícita: el backend devuelve LEGACY_CONTENT_REQUIRES_MIGRATION en vez de sobrescribirlo. Las revisiones históricas conservan su JSON original; solo los snapshots v3 nuevos se restauran automáticamente por esta API.

## Pruebas y comparación

| Evidencia | Resultado |
|---|---|
| Contrato frontend real | Fixture generado/validado con funciones Next originales y roundtrip backend sin pérdida |
| Website | 92 pruebas correctas, incluidas las 48 B1 y 44 B2 |
| Transacciones PostgreSQL | Dos saves con mismo ETag: uno gana y otro412; save/publicación no mezclan snapshots; uploads duplicados producen un medio |
| Publicación/restore | Snapshot íntegro, rollback conserva pointer anterior, restore solo cambia draft, suspensión respetada |
| Tenant/permisos | Lectura/escritura/historial/preview/medios ajenos denegados; membresía y grants actuales; publicador sin edición |
| Medios | Procesamiento real, mocks R2, MIME/tamaño/dimensiones, URLs/IDs ajenos, retención y limpieza ante fallos |
| Migraciones | Estado B1/0008 conciliado; maestros ERP y snapshots antiguos preservados |
| OpenAPI/CORS | DTOs y headers verificados; If-Match permitido y ETag expuesto |
| Regresión B1 actual | 615 pruebas: 495 correctas, 84 fallos, 36 errores |
| Regresión B2 | 659 pruebas: 539 correctas, mismos 84 fallos y 36 errores |
| Delta de casos fallidos | Ningún caso nuevo; nombres completos en b2-regresion.json |

Respecto al informe B1 anterior (83/35), el baseline actual reproduce además `test_daily_consult_filters_closures_to_selected_day` de POS y `test_void_reverses_inventory_exit` de ventas, sensibles a fechas/orden temporal. Aparecen tanto en el snapshot B1 como en B2; no se modificaron esos módulos. La comparación actual evita atribuirlos a B2.

La regresión completa se ejecutó secuencialmente con StaticFilesStorage y MD5PasswordHasher solo en memoria del runner, igual para ambos snapshots y con clave JWT de test. No se alteró la seguridad/almacenamiento de la aplicación. El aviso de staticfiles sin recolectar es del entorno de tests. Los últimos ajustes del adaptador y metadatos OpenAPI se verificaron además con la suite Website y checks correspondientes.

Cobertura aplicable de matriz08: A01–A03, P01–P05, C01–C03, V01–V02, M01–M04, D01–D02 y R01/R02 por regresión diferencial. No se probaron navegación Next, publicación pública por hostname, DNS real o entrega de imágenes desde R2/CDN.

## Dependencias para B3 y límite de entrega

1. Conciliar y autorizar cualquier base habitual antes de aplicar migraciones allí.
2. Conectar el repositorio HTTP Next al UUID descubierto por E0 y conservar status/code/fields de errores. No usar localStorage como autoridad editorial.
3. Sustituir selección inline de archivos por M1, adaptar el límite frontend8 MiB al backend5 MiB y usar URLs/IDs gestionados.
4. Adaptar permisos y etiquetas desde capabilities, acciones save/publish/restore y conflictos ETag; mantener el diseño existente.
5. Implementar resolución/lectura pública B3 exclusivamente desde published_revision y proyección segura de campos visibles, con no-store inicialmente.
6. Validar R2/CDN y dominios en entorno autorizado; demostrar entonces el banner publicado en un segundo navegador.
7. Resolver por separado la deuda de pruebas ERP y la exposición heredada de catálogos con tenant opcional ya documentada. B2 no habilita esas APIs como fuente comercial.

Trabajo detenido en B2. Sin cambios frontend, commits, push, producción, B3, B4 o B5. El banner público entre navegadores continúa siendo el siguiente hito.
