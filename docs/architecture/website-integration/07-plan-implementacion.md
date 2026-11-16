# 07 — Plan priorizado de implementación

Estado B3: [integracion backend/Next y pruebas HTTP](11-entrega-b3.md) implementadas. R2 real y validacion visual en navegador siguen pendientes; no implica aceptacion integral ni habilita B4.

Fecha: 15/11/2026. Esta entrega ejecuta B0 documental. B1–B6 son trabajo futuro, no autorización de implementación, cambios frontend, migraciones o despliegue.

Actualización posterior: B1 fue autorizada e implementada por separado; ver [entrega y verificaciones B1](09-b1-implementacion.md). La validación aislada de B1 no habilita B2–B6 ni implica despliegue o migración de la base habitual.

Estado posterior: [B2 backend implementada y probada](10-entrega-b2.md), con persistencia v3, revisiones, ETag, publicación, restore, preview y medios. La conexión Next descrita en el plan permanece pendiente por alcance explícito del usuario y corresponde al siguiente hito B3. Sin migraciones en base habitual ni despliegue.

## Prioridad y alcance del primer incremento

Primera entrega funcional: **Website + resolución segura de empresa + API pública de contenido publicado + conexión mínima del editor Next**. Verificación: un usuario autorizado guarda/publica un banner de A, y un segundo navegador sin contenido local lo obtiene desde Django/PostgreSQL únicamente para A.

El backend se prepara en `apudig_mvp/develop`, usando `ad_frontend/mvp_website` como referencia contractual. websites_v0 es fuente recuperable, no backend activo. No merge/cherry-pick automático; preservar `.gitignore` y trabajo de terceros. La implementación posterior debe volver a comprobar HEAD y estado local.

Reglas de trabajo:

- No duplicar Company, usuarios, Product, precios ni entidades CMS recuperables.
- Preservar rutas/contratos/permisos operativos; corregir exposición de datos con adaptación explícita y regresión.
- Lectura pública solo desde snapshot publicado; editor/preview desde draft autorizado.
- Probar aislamiento y contratos en cada fase; B6 es consolidación, no primer momento para probar seguridad.
- Mantener JavaScript/componentes/diseño existentes de Next; solo conexión de datos y controles necesarios.

## B0 — Auditoría cruzada y cierre de contratos

**Objetivo:** conocer código, diferencias y límites antes de crear APIs/modelos. **Dependencias:** acceso de lectura a ambos repositorios y websites_v0.

**Entrega realizada:** documentos 01–08 en esta carpeta. Fuentes, contratos actuales/propuestos, recuperación por componentes, riesgos y pruebas inventariados. No se modificaron frontend, modelos, configuración, migraciones o APIs.

**Archivos:** este paquete documental. **Modelos/migraciones/endpoints:** ninguno implementado. **Verificación:** inspección Git/fuentes; revisión de enlaces/referencias y alcance del diff documental. Pruebas Node/lint de la conversación se registran como evidencia limitada al frontend.

**Riesgos abiertos:** no se conoce esquema/historial real de BD, acceso efectivo PostgreSQL ni dominios/media autorizados de prueba. No afirmar compatibilidad de migraciones aplicada ni CMS operativo.

**Aceptación:** decisiones y contratos revisables, primer hito medible, dependencias externas explícitas. La auditoría de fuentes está completada; la conciliación de BD es entrada pendiente de B1.

## B1 — Recuperar dominio Website y resolver tenant

**Objetivo:** disponer de Website/Domain ligados a Company y de un contexto que falle cerrado. **Dependencias:** B0 y conciliación de BD descrita en 04.

**Orden:** inventariar BD de integración; revisar fuentes históricas; recuperar cadena consistente; añadir extensiones incrementales; provisionar empresas/dominios de prueba de forma autorizada; probar resolución sin exposición de draft.

**Archivos previstos:** `apps/websites/{apps,models,selectors,signals}.py`, migraciones recuperadas y nuevas; `apps/api/v1/{base,permissions}.py`; `config/settings.py` y `.env.example` solo en la futura implementación. Revisar helper compartido antes de modificarlo.

**Modelos/migraciones:** Website, WebsiteDomain y dependencias CMS históricas; estado inicial no publicado; extensiones de 04. La cadena 0001–0006 puede incluir tablas de catálogo aún inactivas; no publicar productos ni montar sus APIs por ello.

**Endpoints previstos:** E0 descubrimiento privado; base de P0/P1, sin respuesta pública hasta que exista snapshot publicado. No implementar registro anónimo de empresas o dominios.

**Tests:** A01–A03, H01–H04, D01/D02, R01. **Riesgos:** BD divergente, grants globales, permisos publish fuera de choices, subdominios reservados y cambios compartidos con ERP.

**Aceptación:** usuario de A no consulta web B; token sin Company no hace consultas globales; dominio desconocido 404; dependencias verificadas sobre PostgreSQL; ningún maestro ERP cambiado.

## B2 — CMS, media, revisiones y publicación

**Objetivo:** guardar el documento v3 y publicar una copia consistente, conservando componentes frontend. **Dependencias:** B1 y contrato E/W cerrado.

**Archivos previstos:** `apps/websites/{models,blocks,services,selectors,media_storage}.py`, módulo de adaptación documental y migraciones incrementales; `apps/api/v1/websites/{urls,views,serializers}.py`; helper de upload procesado si se recupera y tests. Cambios de frontend posteriores y acotados: `websiteRepository.mjs`, transporte de errores, `WebsiteEditor`, `WebsitePreview`, `useWebsiteAccess`, campos de imágenes. Esta auditoría no modifica esos archivos.

**Modelos:** ampliar Website, WebsiteSettings, WebsitePage/Section/Revision y Media; auditoría si falta. **Migraciones:** añadir campos y registro de estado sin reescribir snapshots o historial aplicado. Snapshot completo incluye identidad/contacto/SEO, ocultos y configuración; pointer público solo cambia al publicar.

**Endpoints:** E1–E6, M0–M2; E2 sustituye CRUD fragmentado de banners/secciones. Preview autenticado primero, token remoto opcional después. Historias locales no se importan automáticamente.

**Orden interno:** validador v3 y mapeo reversible -> draft transaccional -> historial/ETag -> media autorizada -> publicación/restauración -> conectar repositorio Next y permisos -> manejo de error/conflicto en UI.

**Tests:** P01–P05, C01–C03, V01/V02, M01–M04, A01–A03. **Riesgos:** settings mutables públicos, secciones ocultas perdidas al restaurar, escritura histórica sin ETag, media inline, IDs demo y dos fuentes del borrador.

**Aceptación:** guardar desde Next persiste en PostgreSQL y puede leerse desde otro cliente autenticado; publicar exige permiso y revisión vigente; dos editores no se sobrescriben; restore no publica; imágenes no dependen del navegador que las subió.

En esta fase, especiales vacíos y campañas sin productos en modo informativo. No bloquear la entrega esperando catálogo real ni aceptar IDs demo como referencias ERP. UI permite contenido informativo y muestra funciones comerciales pendientes sin inventar datos.

## B3 — API pública informativa y conexión SSR Next

**Objetivo:** completar el primer flujo integrado banner -> publicación -> página pública por empresa. **Dependencias:** B1/B2.

**Archivos previstos:** selectores/proyección pública, serializers/vistas storefront y URLs; frontend `src/lib/storefront/store.js`, `(public)/layout.js`, `(public)/page.js`, metadata/contacto, paso de content a StoreHome y guardas de modo comercial. Conservar diseño y catálogos laborales.

**Modelos/migraciones:** no nuevo CMS; usar pointer y revisiones de B2. **Endpoints:** P0/P1; P2 solo si hay páginas informativas publicadas que lo necesiten. P3/SEO avanzado pueden esperar a B4.

**Orden interno:** proyección segura -> cliente SSR público sin token -> resolución consistente por request -> render del contenido publicado -> manejo 404/503 -> prueba dos empresas/dos navegadores. No-store al principio, sin webhook/cache nuevos.

**Tests:** P01–P03, H01–H03, S01, R01–R03, E2E01. **Riesgos:** render estático compartido por Host, fallback demo, metadata cruzada, cambiar mode y activar WhatsApp de carrito demo.

**Aceptación del primer incremento B1+B2+B3:** banner publicado de A visible desde un segundo navegador limpio; draft nuevo no visible; B no ve banner de A; desconocido 404; PostgreSQL comprobado; no dependencia de localStorage para contenido; ERP y catálogos conservados.

Autenticación puede seguir almacenando tokens según el sistema actual: el criterio elimina localStorage como persistencia del CMS público, no pide rehacer auth. Sin cambios DNS o despliegues productivos; usar entorno de integración.

## B4 — Catálogo comercial multiempresa

**Objetivo:** conectar productos reales publicados, filtros globales y navegación. **Dependencias:** primer incremento aprobado y política comercial definida.

**Archivos:** WebsiteProduct/CatalogSettings, selectores, API storefront catalog y tests; frontend `storefrontApi.mjs`, servicios productos/categorías, `StoreCatalog`, filtros, ficha y normalizadores. No reemplazar componentes del catálogo laboral.

**Modelos/migraciones:** reutilizar vínculos históricos; campos editoriales adicionales solo si tienen fuente justificada. No segundo inventario; previous price permanece null sin política real.

**Endpoints:** K0–K7; proyección de productos especiales/campañas sobre IDs autorizados; P3 si corresponde. Multi-OR por grupo, rango inclusivo, nulos al final, orden estable, facets/paginación sobre catálogo entero.

**Tests:** K01–K04, S01, A01, R01/R02; contratos de precio/impuesto y 404. **Riesgos:** doble IGV, lista/moneda incorrecta, almacén ajeno, filtrado de página parcial, regresión legacy de ?site=.

**Aceptación:** solo publicaciones de A en A, sin costo/proveedor/stock interno; total/facets correctos con más de una página; precios coherentes con ERP; catálogo laboral mantiene contrato o recibe adaptación explícita probada.

## B5 — Revalidación de carrito y preparación de cotización

**Objetivo:** que WhatsApp use información vigente sin crear ventas, reservas ni checkout. **Dependencias:** B4, unidad de venta y límite de líneas acordados.

**Archivos:** API de quote/throttle, servicios de precio/UOM existentes y tests; frontend CartProvider/CartPage/cart.mjs y servicio de revalidación. No crear otro SalesQuotation ni cambiar stock.

**Modelos/migraciones:** inicialmente ninguno nuevo para carrito/cotización temporal; snapshot firmado recuperable. Conversión a SalesQuotation real será una entrega posterior con cliente/serie/sucursal e idempotencia.

**Endpoint:** Q0. **Orden:** reconstruir productos por IDs independientemente de página -> validar tenant/unidad/cantidad -> resolver precio Decimal -> comparar respuesta y vigencia -> pedir confirmación de cambios -> formar enlace WhatsApp con teléfono publicado. No enviar mensajes mediante herramientas ni automáticamente.

**Tests:** Q01–Q05, K04, S01, R01/R02. **Riesgos:** truncar 200 líneas a50, precio anterior sin evidencia, unidad incorrecta, UNKNOWN tratado como promesa, token/PII en mensaje, firmas sin cache compartida para rate limit multiinstancia.

**Aceptación:** IDs ajenos no revelan datos; retirados/agotados informados; cambios visibles; carrito no pierde líneas entre páginas; total del servidor; no se crean SalesDocument/SaleOrder/Movement ni se descuenta stock.

## B6 — Pruebas integrales y preparación de activación

**Objetivo:** consolidar contrato, aislamiento, migraciones y experiencia integrada. **Dependencias:** cada fase que vaya a activarse, sin esperar B5 para probar B3.

**Archivos:** tests Django/contratos/E2E, documentación de operaciones, entorno de integración; ajustes de errores descubiertos. **Modelos/endpoints:** no nuevos por defecto; evitar ampliar alcance durante QA.

**Verificaciones:** matriz 08, suite ERP, check/migraciones, pruebas sobre PostgreSQL y restauración de backup; navegación/móvil/teclado; fallos de API/media; metadata y caché por Host. Si se habilita caché, añadir webhook consumidor, autenticación/reintentos y pruebas de vigencia/suspensión. No basta habilitar tags en Django.

**Riesgos:** confundir HTTP200/build con permisos correctos, SQLite con carreras PostgreSQL, revisión visual histórica con la UI actual o publicar piloto no validado.

**Aceptación:** evidencia reproducible por escenario, regresión ERP correcta, fallos sin fallback a otra empresa y reversión segura. Preparar un piloto de una empresa y criterios de activación; cualquier despliegue o cambio productivo queda fuera de esta intervención.

## Guion de aceptación del primer banner

1. En PostgreSQL de integración, provisionar empresas A/B, webs/dominios de prueba y roles editor/publicador autorizados. Registrar motor efectivo sin exponer credenciales.
2. Navegador 1: iniciar sesión, seleccionar A, abrir `/admin/website`; E0/E1 devuelven Website A.
3. Subir imagen por M1 o usar recurso autorizado; editar título único `Banner A revisión 1` y guardar por E2 con ETag.
4. Comprobar persistencia en BD/lectura autenticada y que el público aún no muestra el borrador. Cerrar/reabrir editor y recuperar el mismo contenido desde API.
5. Publicador autorizado aplica E3. Registrar revisión, actor y timestamp; pointer/snapshot confirman commit.
6. Navegador 2 o perfil limpio, sin localStorage del editor: abrir dominio A; SSR/P1 muestra banner/imagen publicada. El contenido debe seguir disponible tras reiniciar Next/Django sin borrar PostgreSQL.
7. Guardar `Banner A revisión 2` sin publicar: navegador2 sigue viendo revisión1. Publicar revisión2: aparece al recargar, sin copiar almacenamiento local.
8. Abrir dominio B y uno desconocido: no aparece banner A; desconocido 404. Intentar editor B con usuario A: denegación.
9. Repetir conflicto entre dos editores y negativa a publicar por usuario sin permiso. Verificar `/catalog`, `/admin/catalog_admin`, login y flujo ERP de lectura acordado.

El guion es criterio futuro, no prueba ya ejecutada. Al completarlo se puede afirmar integración CMS Next + Django + PostgreSQL; antes solo existe preparación/auditoría.

## Orden de trabajo recomendado

```text
B0 documental (esta entrega)
  -> conciliación de BD + B1
  -> B2 + B3 + B6 parcial: PRIMER BANNER REAL
  -> B4 + B6 parcial: CATÁLOGO REAL
  -> B5 + B6 integral: COTIZACIÓN REVALIDADA
```

No fijar fechas cerradas antes de conciliar BD y validar el adaptador v3. Cada incremento debe entregar evidencia, migraciones revisadas cuando correspondan, contratos y limitaciones. El primer incremento es prioritario y verificable independientemente de catálogo y carrito.
