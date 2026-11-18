# Entrega B4-C: integración Next y catálogo autorizado

Validación posterior18/11/2026: ver [aceptación condicionada B4-C4](23-aceptacion-b4-c4.md), con evidencia actual, comprobación en Chrome, correcciones acotadas y bloqueos operativos. Los resultados siguientes corresponden a la entrega C1/C2/C3 original.

17–18/11/2026. Bases: backend `websites_backend@e3f479f`, frontend `mvp_website@856b711`. Se preserva el trabajo B4-B sin confirmar. Sin cambios de rama, commits, push, despliegues, credenciales, `.env`, modelos o migraciones.

## C1 — lectura pública

Implementada y validada antes de continuar a C2. Servicios `storefrontApi.mjs`, `storefrontProductsService.mjs`, `storefrontCategoriesService.mjs` adaptados a K0–K3 por hostname, con validación de identidad, DTO, errores y páginas. `store.js` lee SSR no-store por solicitud. `/shop`, detalle, filtros, header/footer y tarjetas reutilizan los componentes existentes. Facets y totales provienen del servidor; filtros repetibles y paginación no filtran una página local.

Detalle: precios autorizados decimal/null, moneda y unidades de K1, sin cálculo de conversiones/impuestos cliente. No hay productos demo ni fallback entre empresas. HTML/RSC y metadata aislados. El catálogo laboral y su autenticación no cambian.

Pruebas C1: lint y build correctos; 54 tests Node; 10 comprobaciones HTTP reales Next→Django→PostgreSQL18.1 en `test_apudig_b4c_http`, sintética y aislada. Incluyen A/B, dominios no válidos/inactivos/sin publicar, productos extranjeros/no publicados, filtros/facets/páginas, unidades, cero/null y ausencia de campos privados. Se corrigió un enlace WhatsApp del footer para mantenerlo como información, sin enlace operativo. QA visual todavía pendiente.

## C2 — administración comercial

Implementada y validada antes de C3. Nuevo repositorio `src/services/websiteCatalogRepository.mjs` inyecta el transporte JWT existente. Nueva sección `WebsiteCatalogPanel.jsx` dentro de WebsiteEditor, sin otra aplicación ni rutas. K4 busca productos propios; K6/K7 vinculan, editan títulos/SEO/orden/destacados y publican/retiran según permisos. K5 administra listas/almacenes exclusivamente cuando el servidor devuelve canManagePolicy. Roles CMS omiten priceListId, incluso null.

ETag comercial fuerte separado del contador CMS. Lectura combinada rechaza versiones diferentes; 412/428 mantienen ambos formularios, bloquean escrituras y requieren recarga explícita con confirmación para descartar. El panel permanece montado al cambiar de pestaña; no guarda en localStorage ni publica CMS. Revalidación efectiva corresponde a Django en cada operación.

Pruebas C2: lint/build correctos; 58 tests Node. Cuatro comprobaciones HTTP administrativas reales: JWT/permisos/tenant, opciones sensibles omitidas y denegación de cambios de política para CMS, dos editores con 412 y 428, rechazo de referencias ajenas, política autorizada y revisión editorial intacta. Formularios visuales autenticados aún pendientes de navegador.

## C3

Implementada y probada por HTTP. Home obtiene destacados desde K0 (hasta12, orden featured) y referencias especiales/campañas desde K1, sin precios/stock en CMS. Descriptores, visibilidad, orden, títulos y selecciones editoriales proceden del snapshot publicado. Retirar una publicación la elimina sin republicar CMS. No se creó otro registro de plantillas: se reutilizan StoreHome, StoreHero, CategoryProducts, SpecialProducts, HorizontalRail y ProductCard.

Cambio backend mínimo: `apps/websites/public_content.py` conserva los descriptores comerciales publicados que B3 retiraba y filtra referencias contra WebsiteProduct propio, publicado y Product activo. Consulta acotada a referencias UUID; los IDs demo históricos se omiten. K0/K1 siguen decidiendo precio, disponibilidad y elegibilidad final. No se lee el borrador ni se activa comercio. Prueba adicional en `test_catalog.py` verifica referencias ajenas, retiradas y revisión inmutable. No se cambiaron endpoints, modelos ni migraciones.

La selección de especiales/campañas en el editor carga todas las páginas K6 autorizadas, valida referencias y permite quitar productos retirados; no usa arrays demo. El iframe de preview sigue siendo informativo y no proyecta precios/productos ERP: comprobar el resultado comercial en la página pública. Los errores de selección no eliminan el borrador. Tras publicar/retirar productos desde el panel, se refrescan las opciones editoriales.

Diseño: se conserva estructura responsive existente, filas horizontales y navegación. CTA, tarjetas, filtros y paneles usan el color publicado de cada empresa (incluidos portales Radix); placeholder de producto sin foto es un paquete neutro. WhatsApp se muestra como dato de contacto y no como enlace de pedido. No hay alta de clientes, checkout, reservas, pagos ni movimientos de inventario.

Tres comprobaciones HTTP C3 correctas: identidad/colores A y B, precio ERP70.80→84.96 reflejado en K1 y Home manteniendo revisión CMS1, retirada de destacado que desaparece de Home y cuyo detalle pasa a404. Escrituras solo sobre fixtures aisladas; se restaura la publicación al terminar.

## Validación y límites finales

- Frontend: lint, build y59 tests Node correctos. HTTP real:10 comprobaciones públicas C1 +4 administrativas C2 +3 de Home C3. Los tests de transporte/errores usan doubles como pruebas unitarias; el flujo principal HTTP no simula Django/PostgreSQL.
- PostgreSQL18.1:167 tests acotados Website + catálogos laborales correctos en `test_apudig_catalog_p0_tests`. `manage.py check` sin incidencias y `makemigrations --check --dry-run` sin cambios. Migraciones aplicadas únicamente al crear las bases desechables de prueba; ninguna en apudig_mvp.
- Suite completa:724 casos,78 failures y35 errors. Comparada con B4-B (723,79/36), no añade casos fallidos ni cambia la clasificación de los compartidos. Dos fallos anteriores no se reprodujeron (`CashSessionHistoryViewTest.test_daily_consult_filters_closures_to_selected_day`, `SalesDocumentServiceTest.test_void_reverses_inventory_exit`); no se atribuyen correcciones a B4-C, pues esos módulos no se modificaron. **La suite ERP global no está aprobada.** Evidencia: b4c-full-regression.json, b4c-scoped-regression.json y b4c-regresion.json; logs en `.tools` del workspace.
- No se modificaron consumidores `/catalog`, `/admin/catalog_admin`, login, selección de empresa ni APIs/maestros ERP. Pruebas existentes de navegación y catálogos se mantienen. El smoke HTTP comprueba protección laboral anónima; la interacción autenticada completa del dashboard/login necesita revisión visual.
- El control de equipo encontró Chrome, pero al capturar la ventana se detuvo porque no pudo verificar la URL con suficiente confianza para aplicar sus políticas. No hubo interacción ni se intentó eludirlo. **QA visual móvil/tablet/escritorio/teclado y formularios autenticados pendiente**, no aprobada por build o HTTP. Habilidad utilizada: `C:/Users/Robert/.codex/plugins/cache/openai-bundled/computer-use/26.1111.21308/skills/computer-use/SKILL.md`.
- R2/CDN real sigue pendiente según autorización previa del usuario; no se subieron imágenes reales, ni se demuestra su funcionamiento con estas fixtures sin fotografías.
- Advertencias existentes: baseline-browser-mapping desactualizado durante build; carpeta staticfiles ausente en tests backend. No impiden los checks acotados. No se instalaron dependencias.

## Matriz de activación

| Estado | Contenido publicado | Catálogo autorizado | Carrito/pedidos/WhatsApp operativo |
| --- | --- | --- | --- |
| Dominio desconocido, pendiente/inactivo o Website sin publicar |404|404|No|
| Website publicado y dominio válido, sin productos publicados |Sí|Vacío|No|
| Website válido, productos publicados, commerceEnabled=false (actual) |Sí|Listado/detalle, precio autorizado o null, unidades, disponibilidad y destacados|No|
| Futuro opt-in persistido autorizado |Sí|Sí según política|Pendiente de implementación y aceptación específica; no se activa en esta entrega|

La futura autoridad será el opt-in persistido y auditado propuesto en19; no se añadió un flag Next paralelo. P1 rechaza actualmente cualquier contrato que deje de devolver commerceEnabled=false: activar comercio exigirá una entrega coordinada de contratos y operaciones. Ningún ajuste de dominio, lista, publicación o configuración habilita pedidos hoy.

## Archivos de esta intervención

Backend funcional: únicamente `apps/websites/public_content.py` y el caso nuevo en `apps/websites/tests/test_catalog.py` (archivo B4-B previo, preservado). Documentación: este informe22, evidencias b4c*.json y helper `run_storefront_integration.py`. El resto del diff backend pertenece a B4-B y no debe interpretarse como una nueva implementación de esta entrega.

Frontend nuevos: `src/services/websiteCatalogRepository.mjs`, `src/components/admin/website/WebsiteCatalogPanel.jsx`, `src/components/commerce/ProductUnitOffer.jsx`; pruebas `storefront-commercial.test.mjs`, `website-catalog.test.mjs`, `storefront-http.integration.mjs`, `website-catalog-http.integration.mjs`, `storefront-home-http.integration.mjs`.

Frontend modificados:

- Servicios `storefrontApi.mjs`, `storefrontProductsService.mjs`, `storefrontCategoriesService.mjs`; librerías `lib/storefront/store.js`, `lib/commerce/catalog.mjs`, `shop-filters.mjs`.
- Rutas públicas layout, Home, shop, shop/[id], contact y storefront.css.
- WebsiteAccess, WebsiteEditor, WebsitePreview, WebsiteFields, ShowcaseEditor y website-editor.css.
- Commerce: StoreCatalog, FilterRange, ProductCard, ProductPurchase, CartProvider, CartPage, shop.css y cart.css.
- Storefront: StoreHeader, StoreFooter, StoreHome, CategoryProducts, ProductArt, storefront-rails.css y storefront-contact.css.
- Tests existentes de storefront-api y shop-filters; continuidad docs/storefront-plan-y-avances.md e integration-matrix.md. La nota dashboard-y-registro-clientes.md era previa.

## Pendientes para aceptación

Revisión visual y autenticada con un navegador autorizado; medios reales R2/CDN; atender los fallos históricos ERP en trabajo separado; revisión operativa de listas/unidades/impuestos/almacenes y publicaciones reales por el administrador. No se crearon ni publicaron productos habituales. No iniciar registro de cuentas ni activación comercial como continuación implícita.

## Reproducción HTTP aislada

Desde backend: `.venv/Scripts/python.exe docs/architecture/website-integration/run_storefront_integration.py --serve-isolated`. Requiere PostgreSQL local y permiso de creación de bases de prueba. El script comprueba el nombre efectivo antes de escribir fixtures; nunca escribe en apudig_mvp. Crea `test_apudig_b4c_http`, migra solo esa base y sirve Django en8770. Contexto temporal con credenciales exclusivamente sintéticas en `.tools/b4c-http-context.json`; no publicarlo. No verifica DNS real ni utiliza R2.

Desde frontend, en otra consola PowerShell: `$env:WEBSITE_API_V1_URL='http://127.0.0.1:8770/api/v1'; npm.cmd run build; npm.cmd run start -- --port 8771`. Ejecutar `node tests/storefront-http.integration.mjs` y `node tests/website-catalog-http.integration.mjs`. Usan Host explícito a.b4c.localhost/b.b4c.localhost, sin cambios DNS/hosts. Para pruebas de UI autenticada se necesita además configurar NEXT_PUBLIC_API_V1_URL al endpoint aislado **antes** del build (solo entorno del proceso).

Finalizar Next y enviar `{"operation":"stop"}` al stdin del helper para retirar servidor/base/contexto. El helper también soporta `{"operation":"price","amount":"12.00"}` para comprobar cambios ERP sin republicación. No ejecutar fixtures con manage.py sobre la base habitual.

Al cerrar esta intervención se detuvieron los procesos8770/8771 de integración, se eliminó la base sintética test_apudig_b4c_http y se verificó la retirada del contexto temporal de credenciales. La base desechable de tests acotados/completos también fue retirada por el runner. No se detuvieron servidores habituales8000/3000.
