# 11 — Entrega B3: integración Website Next.js y Django

Actualización posterior: la [administración visual de Website y dominios](12-administracion-website.md) incorpora creación explícita de Website, gestión de dominios y consulta segura en Django Admin. Las limitaciones de navegador, R2 y DNS automático continúan documentadas por separado.

Fecha: 15/11/2026, America/Lima. Backend `develop`, base `c8296b7`; frontend `mvp_website`, base `57c212a`.

## Resultado y aceptación

Se conectó el editor existente a las APIs B1/B2 y se implementó la lectura pública del snapshot publicado. Next renderiza identidad, banner, contacto y SEO de la empresa del hostname solicitado. Guardar un borrador no modifica el contenido público. No se implementó B4/B5 ni se conectaron productos, precios, cotizaciones, stock o pagos.

**Estado: implementación B3 y verificación HTTP completadas; aceptación integral pendiente.** El navegador no pudo verificarse de forma segura mediante Computer Use y el usuario indicó continuar con R2 simulado. No se declara demostrado el flujo visual en dos navegadores, responsive, teclado, carga real de archivos desde el selector del navegador ni lectura real R2/CDN.

- **102 pruebas Website correctas en PostgreSQL 18.1**, incluidas publicación, concurrencia, tenant, medios, compatibilidad de claves y proyección pública.
- Suite global B2 preservada: **659 pruebas, 84 fallos, 36 errores**. B3: **669 pruebas, los mismos 84 fallos y 36 errores**. Ningún caso fallido nuevo; la suite ERP continúa sin aprobación global.
- **43 pruebas Node correctas**, lint y build Next correctos.
- Flujo HTTP real Next ↔ Django ↔ PostgreSQL correcto, sin simular persistencia, autenticación o publicación. Smoke adicional: **16 rutas/casos correctos**.

Evidencia: [regresión diferencial](b3-regresion.json), [pruebas Website](b3-website-results.json), [flujo HTTP y banner](b3-http-evidence.json), [frontend](b3-frontend-results.json), [auditoría PostgreSQL](b3-schema-audit.json), [OpenAPI](b3-openapi.json), [manifest del baseline B2](b3-baseline-manifest.json).

## Preservación y entorno

Se revisaron AGENTS.md y los documentos 01–10, los servicios reales B1/B2 y `src/lib/website/content.mjs`. El repositorio preparado está en `src/services/websiteRepository.mjs`, no en la ruta `src/lib/website` indicada inicialmente.

Se preservaron los cambios locales y el índice Git previo de B1/B2; no se hizo checkout, merge, rebase, cherry-pick, commit, push o despliegue. `.gitignore` backend conserva el hash Git `3b726931da3d79b084bc803c3b5fae7d3039e612`. No se editaron los `.env` existentes ni fuentes ERP ajenas a Website.

Versiones: Python 3.12.1, Django 5.2.19, DRF 3.18.3, PostgreSQL 18.1; Node 22.20.0, Next 16.0.10 y React 19.1.0. Sin paquetes nuevos ni actualización de dependencias.

La integración utilizó exclusivamente una instancia PostgreSQL temporal en loopback, puerto 55439, base sintética `apudig_b3_integration` y bases de test desechables. Django escuchó en 127.0.0.1:8013 y Next en 127.0.0.1:3013. Se provisionaron A/B con Websites y dominios `a.b3.localhost` y `b.b3.localhost`; su activación local explícita no demuestra control DNS productivo. No se modificaron DNS, zonas Cloudflare, buckets ni archivos de productos. La base habitual no se consultó ni migró.

Existía un proceso Next dev del usuario: no se detuvo. Las pruebas utilizaron un proceso de producción Next independiente. No se publicaron servicios a interfaces externas.

Al finalizar se detuvieron los procesos de integración Django/Next y PostgreSQL temporal, y se retiraron su directorio de datos, snapshot de ejecución y auxiliares temporales. Los informes JSON, SQL, manifiesto, OpenAPI y scripts de prueba reutilizables se conservaron en los repositorios. La configuración temporal de pruebas no quedó escrita en los `.env` del usuario.

## Backend

### Archivos nuevos

| Archivo | Responsabilidad |
|---|---|
| `apps/websites/public_content.py` | Proyección informativa desde una revisión PUBLISH íntegra y validada |
| `apps/websites/storage_keys.py` | Prefijos persistentes, categorías permitidas y compatibilidad de claves B2 |
| `apps/websites/migrations/0009_website_storage_namespace.py` | Campo de prefijo, unicidad y categorías de medios |
| `apps/websites/tests/test_public_content.py` | Publicación pública, estados, headers, proyección y aislamiento |
| `apps/websites/tests/provision_integration.py` | Preparación explícita de dos tenants sintéticos, limitada a la instancia de integración |

Modificados: `apps/api/v1/websites/{views,serializers,urls}.py`, `apps/websites/{models,selectors,services,media_storage}.py` y pruebas `test_api.py`/`test_media.py`. Los hashes de fuentes existentes se compararon contra el snapshot B2: los cambios están limitados a Website/API Website; migraciones anteriores y módulos ERP conservados.

### Endpoints públicos nuevos

- P0: `GET /api/v1/storefront/resolve/?hostname=...` → contexto público registrado.
- P1: `GET /api/v1/storefront/sites/{hostname}/content/` → PublicContent.

Ambos son anónimos, sin autenticación administrativa, con `Cache-Control: private, no-store`. Validan hostname, dominio ACTIVE/verificado, empresa activa, Website publicado y pointer consistente con el Home publicado. Un hostname desconocido, no publicado o inactivo devuelve 404; no existe fallback a la primera empresa ni a una demo. No se toman `X-Forwarded-Host` o `X-Company-ID` como selector.

P1 valida el documento completo del snapshot y exige operación PUBLISH. Filtra banners y avisos ocultos, secciones deshabilitadas y campañas fuera de vigencia. Elimina referencias comerciales y secciones de catálogo/especiales, con `commerceEnabled=false`. Conserva identidad, contacto, SEO y contenido informativo de una misma revisión. No lee Settings mutable como fuente pública y no devuelve Company ID, RUC, actores, eventos, draft, claves R2 o preferencias ERP.

Los snapshots nuevos capturan también locale/currency; los snapshots v3 B2 anteriores conservan sus valores compatibles es-PE/PEN sin reescritura. canonicalHostname se obtiene del dominio principal activo registrado. El UUID Website se mantiene porque forma parte del contrato público acordado.

E0 conserva su DTO y añade comprobación opcional `hostname`: si pertenece a otro Website, devuelve 403 `DOMAIN_COMPANY_MISMATCH`. Next la envía desde `window.location.hostname` y bloquea el editor de una empresa diferente. Esto es una restricción de interfaz/contexto, nunca autorización basada en Host: JWT, membresía actual y permisos Django siguen siendo obligatorios en cada operación. La administración central puede operar desde un hostname sin asignación Website; el allowlist del borde y la política de dominios administrativos productivos deben configurarse al desplegar, fuera de esta entrega.

## Frontend

### Archivos principales

| Archivos | Cambio |
|---|---|
| `src/services/websiteRepository.mjs` | E0, E1–E6 y M0–M2 reales, UUID, trailing slash, If-Match, multipart y ETag |
| `src/services/api.js` | Conserva status/code/message/fields/ETag/Retry-After; respuesta con metadata opcional, compatible con consumidores existentes |
| `src/components/admin/website/useWebsiteAccess.js` y `WebsiteAccess.jsx` | Descubrimiento autorizado y capacidades efectivas del servidor |
| `WebsiteEditor.jsx`, `WebsitePreview.jsx`, `EditorialImageField.jsx`, nuevo `WebsiteMediaContext.jsx` | Editor real, preview protegido, publicación, restauración e imágenes gestionadas |
| Nuevo `src/lib/website/errors.mjs` | Mensajes para 401/403/404/412/428/413/429/503 sin perder el error original |
| Nuevo `src/lib/storefront/public-website.mjs` | Normalización del Host y transporte público anónimo con timeout/no-store |
| `src/lib/storefront/store.js` | Lectura SSR, memoización por request y fuente informativa sin productos demo |
| `src/app/(public)/{layout,page}.js` y páginas about/contact/shop/cart | Contenido real, metadata propia y comercio pendiente señalizado |
| `StoreHeader.jsx`, `CartProvider.jsx` | Búsqueda/carrito deshabilitados mientras commerceEnabled sea false |
| `.env.example` | URL pública y URL Django exclusiva de servidor |
| `tests/website.test.mjs`, `storefront-smoke.mjs`, nuevos `website-public.test.mjs` y `website-http-integration.mjs` | Contratos actualizados y pruebas reales/opcionales |

Se conservó JavaScript/JSX, diseño, estilos responsive y componentes existentes. No se añadió otra biblioteca de medios ni otro login.

El editor usa el Website de E0 y carga E1. E2 guarda, E3 publica y E6 carga el preview guardado. La preview del formulario usa postMessage con origen/ventana/empresa validados dentro de un iframe autenticado, con enlaces inertes. El historial resume revisiones del servidor; recuperar la publicación consulta E4 paginado y ejecuta E5, creando borrador sin publicar. No se creó una pantalla nueva de comparación de revisiones.

Los controles se adaptan a view/edit/publish/mediaUpload/domains/realPublication del backend. El editor conserva el formulario tras un 412 y pide confirmación explícita antes de reemplazarlo con una recarga. Los errores de campo pertenecen al documento exacto rechazado y dejan de bloquear cuando se modifica ese documento. La biblioteca permite listar, subir y desactivar medios con su permiso específico; una referencia retenida responde 409.

No se lee ni importa localStorage editorial en modo real. El repositorio local sigue disponible como utilidad de demo/pruebas explícita, separado y sin activación automática. Los borradores locales antiguos no se borran ni sobrescriben. La sesión administrativa existente continúa usando sus tokens y selección de empresa habituales.

### Lectura pública y rutas

Next obtiene el Host de la petición, elimina únicamente el puerto válido y solicita P1 desde servidor sin JWT. No consulta cabeceras forwarded. React cache deduplica dentro de una petición; fetch no-store evita reutilizar contenido entre dominios. Layout, metadata y Home comparten esa lectura. Canonical proviene del registro Django y la indexación permanece desactivada durante la integración.

No se sirven productos demo ni se activan precios/cotizaciones. `/shop` muestra catálogo pendiente y `/shop/{id}` desconocido devuelve HTTP404; `/cart` muestra la disponibilidad futura. Los enlaces conservan sus rutas. `/catalog` y `/admin/catalog_admin` mantienen sus componentes/contratos heredados, fuera del storefront informativo.

Un fallo de API no selecciona contenido demo ni metadata de otra empresa. Website desconocido produce notFound; errores de servicio usan el manejo de errores Next. No se incorporaron proxy.js, rewrites ni dependencias adicionales.

## Política R2 definitiva de esta entrega

La inspección de código verifica que productos genera `products/{companyUUID}/{productUUID}/{slot}.webp`; las URLs absolutas antiguas también son legibles. Company no dispone de un prefijo R2 persistente. No se asume que los objetos reales actuales de todas las empresas sigan ese generador ni que `ft_soledad` esté asignado a una empresa concreta: no se consultaron objetos productivos ni la base habitual.

Se utiliza el mismo cliente, bucket, URL pública, validación Pillow, optimización WebP y thumbnails de APUDIG. No hay nuevas credenciales, cuenta, bucket o procesador. `Website.storage_prefix`, configuración interna persistente del Website OneToOne con Company, define el namespace Website de esa empresa sin modificar el almacenamiento ERP.

Para nuevas cargas:

```text
{storage_prefix}/website/{category}/{mediaUUID}.webp
{storage_prefix}/website/{category}/{mediaUUID}-thumbnail.webp
```

- Default seguro: `companies/{companyUUID}`; se persiste bajo bloqueo antes del primer upload correcto.
- Un operador podrá provisionar un prefijo existente como `ft_soledad` tras verificar su asociación. No proviene de formulario, nombre comercial o dominio público.
- Prefijo único global, segmentos ASCII permitidos, sin puntos/traversal; no cambia después de cargas bajo ese prefijo. No hay endpoint público/administrativo de usuario para modificarlo.
- Categorías permitidas: LOGO/FAVICON→logo, BANNER→banners, PROMOTION→promotions, SECTION→sections, IMAGE→media. Nombre de archivo UUID generado en servidor.
- Ejemplo provisionado: `ft_soledad/website/banners/{mediaUUID}.webp`. El default no requiere deducir ni renombrar los prefijos de productos.
- WebsiteMedia conserva ownership mediante Website→Company, metadata, checksum, deduplicación, referencias y protección de eliminación. El namespace no reemplaza autorización.
- Las claves B2 `websites/{websiteUUID}/media/{mediaUUID}.webp` siguen admitidas para lectura, asociación y revisiones. No se mueven objetos ni se regeneran sus URLs.
- Uploads nuevos reutilizan el contrato M1, con máximo 5 MiB, PNG/JPEG/WebP reales. El servidor devuelve URLs; no se publican data URLs.
- Si R2/BD falla se conserva la limpieza compensatoria de claves nuevas; un proveedor caído aún puede dejar huérfanos que necesitan conciliación operativa. M2 es soft-delete y bloquea medios referenciados.

**R2/CDN real pendiente por decisión expresa del usuario.** Los tests usan imágenes reales procesadas por Pillow y un cliente R2 simulado, incluyendo claves, URLs, errores y referencias en PostgreSQL. No demuestran escritura/lectura real del bucket `apudig-empresas` ni carga visible en otro navegador. Antes de habilitarlo en una instalación existente se debe conciliar sus medios/prefijos autorizados.

## Migración

`0009_website_storage_namespace` añade storage_prefix y unicidad condicional para valores no vacíos, y amplía las categorías de WebsiteMedia. No transforma datos ni objetos; el campo vacío conserva medios anteriores y permite provisionar el namespace posteriormente. No modifica maestros/operaciones ERP.

Se ejecutaron plan, historial, grafo, migración en PostgreSQL aislado y auditoría posterior: 14 tablas Website compatibles, sin incidencias. Se revisó el [SQL de 0009](b3-migration.sql) con el estado completo ERP, conservando la precaución de proyección histórica documentada en B2. Se ajustó la migración nueva durante su preparación local y se volvió a probar; migraciones 0001–0008 y sus alias históricos permanecen intactos. No se usó --fake ni se cambió el historial de otra base. Ninguna migración se aplicó a la base habitual o producción.

## Pruebas y límites de evidencia

| Verificación | Resultado |
|---|---|
| Website/PostgreSQL | 102 correctas; [resultado](b3-website-results.json) |
| Suite global diferencial | 669 vs 659; mismos 84 fallos/36 errores, cero nuevos |
| Django check / makemigrations --check / migrate --check | Correctos |
| Historial y auditoría | Consistentes, 14 tablas compatibles |
| OpenAPI | Documento validado, 11 rutas Website/Storefront |
| Node | 43 correctas |
| ESLint / Next build | Correctos; aviso heredado baseline-browser-mapping, sin actualizar paquetes |
| HTTP integración | Login, empresa, refresh, discovery, draft, publish, preview, conflicto y aislamiento correctos |
| HTML/metadata | Banner/contacto/SEO publicado de A; B independiente; sin RUC/Company IDs/actor/storage_key |
| Cabeceras/hostnames | Host registrado, forwarded manipulado ignorado; desconocido404 |
| Reinicio | Procesos Django/Next reiniciados; la revisión PostgreSQL previamente publicada permanece legible |
| Rutas | 16 casos HTTP correctos, incluidos catálogos heredados y productos inexistentes404 |
| Navegador limpio / UI / responsive / accesibilidad visual | Pendiente: Computer Use detuvo el acceso por no poder verificar la URL de Chrome en Windows |
| R2 real / CDN / imagen visible | Pendiente: simulación autorizada por el usuario |

Las pruebas HTTP emplean el repositorio JS real y peticiones a servidores reales; no ejecutan React en navegador. El smoke de catálogos demuestra conservación de ruta/HTML, no aceptación funcional completa de cada operación ERP autenticada. Los defectos heredados de esas APIs siguen reflejados en la regresión global y documentación previa; no se consideran resueltos por B3.

El runner diferencial usa MD5PasswordHasher y StaticFilesStorage únicamente en memoria, con entradas idénticas y claves JWT desechables. No cambia la seguridad de la aplicación. Se conservaron hashes del baseline y casos fallidos identificados; no se publicaron tokens ni cadenas de conexión.

## Configuración y repetición en integración

1. Crear PostgreSQL desechable autorizado en 127.0.0.1:55439, usuario de integración `apudig_b3`, base `apudig_b3_integration`. Exportar DJANGO_DB_ENGINE/NAME/HOST/PORT/USER/PASSWORD y JWT_SECRET_KEY de pruebas antes de cualquier comando Django. No utilizar los valores de la base habitual.
2. Revisar historial/esquema, `migrate --plan` y las migraciones, aplicar exclusivamente a esa base. `apps/websites/tests/provision_integration.py` está limitado expresamente a dicha instancia y prepara A/B; no es un comando para datos reales.
3. Arrancar Django en 127.0.0.1:8013. Configurar CORS_ALLOWED_ORIGINS con los orígenes locales realmente usados. No incluir credenciales R2 productivas en pruebas.
4. Configurar `NEXT_PUBLIC_API_V1_URL` y `WEBSITE_API_V1_URL` a `http://127.0.0.1:8013/api/v1` antes del build. La primera se compila para el cliente; la segunda solo se usa en servidor. No poner JWT/R2 secrets en variables NEXT_PUBLIC.
5. Ejecutar lint/build y arrancar Next en 127.0.0.1:3013. El entorno real debe aceptar Host en un borde confiable; no permitir que un proxy copie forwarded externos sin validación. No se cambió infraestructura en B3.
6. Para pruebas Node: `node --test tests/*.test.mjs`. Smoke: `node tests/storefront-smoke.mjs http://127.0.0.1:3013 a.b3.localhost`.
7. Para integración HTTP, exportar B3_API_URL/B3_NEXT_URL, B3_FIXTURE (archivo de fixtures sintéticos generado) y B3_EVIDENCE (destino temporal); ejecutar `node tests/website-http-integration.mjs`. El script limita sus destinos a loopback/puertos de integración.
8. El [runner de comparación](run_integration_checks.py) recibe checkout/snapshot y ruta de evidencia; para Website añadir `apps.websites`. Para repetir el diferencial, ambos snapshots deben corresponder a sus manifests y ejecutarse secuencialmente en el mismo entorno aislado.

## Pendientes antes de aceptar B3 y recomendar B4

1. Ejecutar el flujo real desde `/login` y `/admin/website` en un navegador habilitado: permisos, banner desktop/mobile, archivos, conflictos conservando formulario, restauración, preview, teclado y tamaños móvil/escritorio.
2. Validar R2/CDN autorizado con un archivo nuevo, confirmar propiedad/prefijo y limpieza, sin mover objetos anteriores. Verificar imagen y texto alternativo desde un navegador sin sesión editorial.
3. Repetir apertura A/B y reinicio en dos contextos de navegador, sin localStorage editorial. La evidencia HTTP disponible no sustituye esa prueba visual.
4. Conciliar y autorizar por separado la base habitual y prefijos históricos antes de aplicar migraciones allí; definir dominios administrativos, borde/CORS y límites operativos productivos.
5. Mantener priorizada la deuda ERP y la exposición heredada de catálogos con contexto opcional ya documentada. El comercio continúa deshabilitado hasta diseñar/probar B4.

No iniciar B4 con la aceptación integral de B3 pendiente. No hubo despliegues, commits o pushes.
