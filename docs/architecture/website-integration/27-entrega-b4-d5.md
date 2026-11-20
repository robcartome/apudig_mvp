# B4-D5: integración técnica y aceptación del piloto

20/11/2026, America/Lima. Continúa26 y el ajuste posterior de carrito anónimo/categorías de Home. **Implementación técnica integrada con opt-in en PostgreSQL aislado. La aceptación operativa y la activación habitual no están aprobadas.** SMTP real, R2 real y QA visual no se acreditan con pruebas HTTP o adaptadores simulados.

## Base y límites

Ramas/commits verificados: backend `websites_backend@a6ac628`, frontend `mvp_website@ce91c0c`. La rama backend real difiere del develop del contexto histórico: se conservó. Trabajo D1–D4 y carrito público sin confirmar preservado. No hubo checkout, merge, commit, push, despliegue, edición de `.env`/secretos, carga R2, mensajes WhatsApp o migraciones habituales.

PostgreSQL18.1 habitual `apudig_mvp` inspeccionado READ ONLY. `demo.localhost` sigue activo/verificado, publicado en revisión26,20 productos publicados, sin lista pública predeterminada y sin WebsiteMedia activos. Pendientes0011–0015. No se crearon empresas, usuarios, Customers, precios, stock o políticas reales. Las diferencias respecto a antiguos informes son datos preexistentes del entorno, no escrituras de esta intervención. Ver `d5-local-environment.json`.

Versiones reales: Django5.2.19, DRF3.18.3, psycopg3.3.8, PostgreSQL18.1, Pillow13.0.0, boto3 1.44.1; Next16.0.10, React19.1.0. Sin dependencias instaladas.

## D5.1: autorización persistente

`WebsiteCatalogSettings.commerce_enabled` es la única autorización persistente, defaultFalse también en PostgreSQL mediante db_default. No se añade otro flag Next o una variable de entorno comercial. Publicar CMS/productos o crear una cuenta no modifica esa autorización.

K5 PATCH acepta `commerceEnabled` booleano JSON estricto, solo ADMIN de la empresa/superusuario con contexto válido y membresía/permisos actuales. Usa bloqueo Website, ETag comercial/If-Match y AuditLog WEBSITE_CATALOG_POLICY con before/after. Sin precondición428, obsoleta412. La escritura es atómica, incluida la validación de listas/almacenes.

Para autorizar solicita esquema comercial disponible, Company activa, Website publicado/revisión HOME válida, dominio activo/verificado, WhatsApp publicado válido, aviso versionado de la misma empresa con conservación definida, almacenes autorizados y al menos una oferta pública con precio válido. Los bloqueos retornan409 COMMERCE_NOT_READY con campos legibles. Es una comprobación técnica; guardar un texto por ADMIN no demuestra aprobación jurídica ni aceptación del piloto.

K5 devuelve a administradores `commerceReady` y `commerceBlockers`. `commerceEnabled` de K5 representa el opt-in guardado; P1/perfil/oferta representan su efectividad actual. P1, prepareOrders y ordersEnabled consultan la misma fuente y fallan cerrados si se pierde preparación. Se puede desautorizar incluso si faltan condiciones. Activar comercio no activa registro: este conserva WEBSITE_REGISTRATION_ENABLED, proveedor real configurado, política/consentimiento y protección de abuso independientes.

Se preservaron lecturas públicas/K0/K5 con esquema previo a0014 mediante proyecciones sin la nueva columna y gatefalse. Escrituras K5 requieren el esquema nuevo y devuelven503 si falta. La introspección no modifica el historial. No se garantiza ejecutar todas las pantallas administrativas nuevas antes de migrar; la secuencia operativa sigue siendo expansión de esquema antes del despliegue.

## D5.2: interfaz y solicitudes

Next acepta commerceEnabled true/false estrictos del servidor. El panel comercial existente muestra la autorización y los bloqueos solo al administrador autorizado; no crea otro editor. Cuenta, acceso/registro e historial reflejan capacidades actuales, sin textos que afirmen que todo está apagado cuando una integración está habilitada.

El flujo público mantiene selección anónima; continuar lleva al guard/login comercial. La incorporación al carrito privado Website/cuenta sigue siendo explícita y conserva ambas selecciones. Django recalcula precio/lista, impuestos, moneda, unidades y disponibilidad; React no decide valores comerciales. Carrito y formularios conservan trabajo ante errores y conflictos. ProductPurchase real siempre usa las unidades/API reales, incluso con comerciotrue: nunca entra en el generador demo de WhatsApp.

La interfaz prepara una solicitud únicamente tras oferta confirmada, aviso vigente y decisión expresa de compartir. Usa Idempotency-Key estable al reintentar el mismo cuerpo; no crea duplicados. Muestra referencia/estado y permite al usuario abrir el enlace que entregó Django. No abre WhatsApp automáticamente ni marca recepción. Historial propio permite consultar un resumen vigente y cancelar; retirada de autorización conserva lectura/cancelación pero bloquea nuevas solicitudes/enlaces.

El detalle revalida la huella comercial y contacto/revisión publicados antes de entregar nuevamente un enlace. Ante cambio de precio, retirada o contacto incompatible devuelve el historial original con whatsappUrl=null/reviewRequired=true. No se altera la evidencia histórica. Un enlace previamente copiado no puede revocarse dentro de WhatsApp; el texto siempre indica que no hay reserva ni aceptación empresarial.

Estados: PREPARED, CANCELLED y EXPIRED derivado al leer, sin escrituras GET. Se evaluaron RECEIVED/ACCEPTED/REJECTED y no se agregaron: no hay una operación administrativa de recepción/aceptación definida y probada que justifique esos estados. Nunca se generan SalesQuotation, ventas, comprobantes, pagos o movimientos/reservas de inventario.

Registro/verificación/recuperación reutilizan User/Customer/CommercialAccount y login existente. Con una prueba de correo se puede elegir explícitamente usar la identidad APUDIG existente sin introducir una contraseña nueva; el servidor exige sus credenciales actuales. Un alta sin coincidencias usa el servicio canónico Customer; coincidencias requieren revisión, nunca adjudicación por correo/documento. Mayorista es aprobación separada/revocable. Perfil conserva lectura de datos propios; cambios de contacto/fiscalidad no se incorporan como una edición insegura. Se corrigió la pérdida del token de fragmento durante la repetición de efectos de Strict Mode en desarrollo.

## D5.3: correo, abuso y medios

El adaptador SMTP exige remitente válido, puerto1–65535, hostname sin espacios/inyección y TLS xor SSL; locmem/disabled no habilitan registro real. Outbox conserva hashes de secretos, reintentos acotados, cooldown, recuperación de claims atascados y errores saneados. Una entrega SMTP tiene semántica de al menos una vez ante un fallo entre envío y registro del resultado; no se promete exactly-once externo. Reintentar genera otra prueba y deja válida únicamente la vigente. Pruebas separadas verifican que un job SENT no se reenvía y que no supera tres intentos.

Nueva protección `WebsiteRegistrationQuota`: contadores horarios compartidos en PostgreSQL con clave HMAC, unicidad key/window y bloqueo transaccional. No almacena IP o email crudos. Límites por IP20/h, destino3/h, Website200/h y global1000/h; pruebas de tokens40/h por origen. DRF mantiene su límite adicional, pero la protección ya no depende exclusivamente de memoria local. Al consumir un presupuesto se limpian contadores de ventanas anteriores a24h; sin tráfico permanecen hasta la siguiente limpieza. Son metadatos técnicos de protección, no la conservación de identidad/consentimientos.

WEBSITE_TRUSTED_PROXY_CIDRS vacío ignora X-Forwarded-For. Cuando se configura expresamente, recorre la cadena desde el peer confiable y toma el primer salto no confiable; cadenas malformadas/largas no autorizan un origen arbitrario. El proxy debe sobrescribir/limpiar cabeceras y limitar acceso directo según la topología real. Los límites de ventana fija admiten ráfagas en los bordes; complementar con edge/WAF/cuotas del proveedor antes del piloto público. Valores documentados en `.env.example`; no se editaron secretos.

R2 reutiliza Website media_storage e inventory.product_image_storage. Las pruebas existentes ejecutadas cubren logo/banner mediante medios CMS, referencias/ownership, claves históricas, deduplicación, WebP/thumbnail, URL pública, formato/tamaño, fallos de almacenamiento y limpieza por fallo DB. **Usan adaptador R2 simulado; no prueban el bucket/CDN real.** No se creó otro almacenamiento.

## Contratos finales

Base `/api/v1/`, slash final, JSON/no-store y separación Authorization por finalidad. Exportación acotada `d5-contracts.json`:19 rutas de cuenta/registro/administración y P1/K5 con componentes referenciados. Los contratos K0–K7 y D1–D4 conservan rutas. OpenAPI global mantiene96 warnings/114 errores documentales heredados; no se declara aprobado todo el esquema ERP.

- K5 `GET/PATCH websites/{websiteId}/catalog-settings/`: añade commerceEnabled en PATCH; ETag/If-Match comercial; respuestas administrativas añaden commerceReady y commerceBlockers. Referencias de listas/almacenes siguen propias y solo visibles según permiso.
- P1 `GET storefront/sites/{hostname}/content/`: commerceEnabled booleano efectivo; solo revisión CMS publicada, sin precios/stock en el documento.
- Perfil `GET storefront/sites/{hostname}/account/`: capabilities.prepareOrders y registration derivados, sin grants laborales. Quote/confirm conservan confirmed/offerFingerprint/ordersEnabled.
- POST `.../account/order-requests/`: items/productId/unitId/quantity, offerFingerprint, note, shareConfirmed:true e Idempotency-Key UUID. Verifica sesión, dominio, titular/Customer, gate, aviso y recálculo bajo bloqueo.403 cerrado;409 oferta/aviso/idempotencia;201 creación/reintento del mismo registro.
- GET detalle/historial y POST cancelación conservan ownership. Detalle añade reviewRequired; whatsappUrl solo si está autorizado/vigente. Cancelar no admite un nuevo estado en el cuerpo.
- Registro conserva202 uniforme antes de prueba, proof de un solo uso, identidad existente autenticada y revisión Customer.503 cerrado/proveedor/esquema;429 protección compartida. No se publican buscadores de usuarios/clientes.

## Pruebas y evidencia

Resultados exactos finales y comparación de identificadores se conservan en `d5-final-postgresql.json`, `d5-full-regression.json`, `d5-regression-comparison.json` y `d5-frontend-checks.json`. No se confunde una comparación sin nuevas regresiones con suite global aprobada.

-264 pruebas PostgreSQL acotadas correctas: Website, catálogo laboral/aislamiento e imágenes. Incluyen11 nuevas de autorización, límites, correo y migraciones. Adaptadores SMTP/R2 simulados se identifican en sus tests.
-34 pruebas PostgreSQL enfocadas repetidas tras los últimos ajustes de readiness: activación/migraciones, solicitudes, entrega y registro, todas correctas; d5-final-focused.json.
-805 pruebas ERP completas:78 failures/35 errors. Baseline HEAD a6ac628 repetido hoy en snapshot limpio:752 pruebas, exactamente78 failures/35 errors, mismos identificadores y cero nuevos casos fallidos. No se atribuye una corrección D5 a los dos casos ausentes frente al115 anterior (consulta diaria POS y reversión de salida en ventas): tampoco aparecen hoy en HEAD limpio. Ver d5-current-baseline.json y d5-regression-comparison.json. La suite global no está aprobada.
-85 pruebas Node correctas, lint/build correctos. Compilación aislada y restauración de build habitual. Aviso baseline-browser-mapping antiguo, sin instalar dependencias para ocultarlo.
-36 grupos de comprobaciones HTTP:10 sesión D1,5 carrito/registro cerrado D2–D4,11 storefront público,6 autorización/solicitud/cambio de precio/desactivación D5 y4 registro/recuperación D5. APIs Django y PostgreSQL reales; transportes Next y SSR reales. Las pruebas de correo usan locmem únicamente en el adaptador externo del worker, seleccionado con --simulate-email. No equivalen a entrega SMTP real o interacción visual completa.
-Alta HTTP real→cola→prueba sintética de un solo uso→Customer mínimo→login comercial→oferta→solicitud PREPARED; recuperación revoca sesión anterior. Los fixtures no conceden membresías ERP. Resto de pruebas usa cuentas verificadas sintéticas, no envíos reales.
-Django check, grafo y makemigrations --check --dry-run correctos. Migraciones y restricciones ejecutadas en bases desechables PostgreSQL18.1 `test_apudig_catalog_p0_tests` y `test_apudig_b4c_http`. El test de migración revierte0014/0015 hasta0013, comprueba ERP/solicitudes/lectura pública y reaplica; también prueba inserción de settings por modelo anterior con DB defaultfalse.

Defectos encontrados y corregidos: flag público fijo, rama demo de ProductPurchase cuando se habilitaba comercio real, textos de estado fijos, ausencia de cuota compartida, detalle que volvía a ofrecer un enlace con oferta antigua y token de fragmento perdido por repetición de efectos. La ruta /cart todavía exportaba una página provisional en vez del CartPage existente: se conectó al componente real y se reforzaron los checks SSR con su estructura sf-cart-page, incluyendo el estado con comercio deshabilitado. Se volvió a ejecutar la regresión HTTP pública/cuentas y el flujo con opt-in tras corregirla. Durante la escritura de tests se corrigieron un nombre de argumento de fixture y un estado parcial de migraciones de prueba que no incluía dependencias ERP; no fueron fallos productivos ocultados.

## Matriz de seguridad A/B

| Perfil/caso | Evidencia y resultado |
| --- | --- |
| Anónimo | K0–K3/selección pública sí; solicitudes/cuenta privadas401; registro cerrado503 salvo integración de correo expresamente simulada |
| Minorista verificado | Sin aprobación mayorista prepara con precio público y consentimiento en integración autorizada; referencia persistida, mismo key/mismo registro |
| Mayorista aprobado/revocado | Pruebas de cuentas/cálculo y HTTP D1: lista propia actual, revocación aplicada con token vigente; sin fallback interno |
| No verificado/suspendido | Sesión/operación denegadas; tests commercial_sessions y commerce_activation |
| Trabajador/CMS | Token laboral no sustituye JWT comercial; CMS no activa política ni vincula Customer; catálogo laboral preservado |
| Usuario mixto | Intercambio explícito, almacenes de sesión separados, refresh/logout preservan finalidad; D1 y sus10 checks repetidos |
| ADMIN/superusuario | Política según contexto/Company/membresía actuales; ETag428/412, auditoría y rollback; no autorización global por un UUID |
| A→B y mismo User A/B | B no lee UUID/historial de solicitud A; hostname desconocido/inactivo/sin publicar404; HTML/RSC sin secretos/contactos privados de cuenta |
| Customer/lista/unidad/precio ajenos | DTO estricto y servicios scoped; Django valida relaciones y no confía en importes/stock del navegador |
| Cambios/precondiciones | Precio cambiado409, nuevo recálculo, enlace histórico retenido; retiro comercial y Company inactiva fallan cerrados |
| Caché/transporte | Público hostname/no-store; privado Bearer/no-store/Vary Authorization; tokens/pruebas fuera de HTML/RSC/URLs de consulta |

Los JWT comerciales permanecen en almacenamiento por Website del navegador, separado del laboral, según el transporte existente. Esto no protege contra XSS. Se revisó el código comercial sin añadir inserción de HTML crudo o cookies amplias; se mantienen validaciones de URL/documento y textos escapados. No se migró todo el login a cookies durante D5: requiere BFF/CSRF/CORS/refresh y validación de compatibilidad propios. XSS, CSP, dependencias y configuración de seguridad del despliegue requieren revisión antes de producción; separar finalidades no resuelve esos riesgos por sí solo.

## Migraciones y operación autorizada

0010–0013 se conservaron;0010 ya estaba aplicada al iniciar. Nuevas0014_commerce_opt_in y0015_registration_abuse_limits: aditivas, sin reescritura de datos maestros, precio, stock o historial previo.0014 añade booleano defaultFalse en app/DB;0015 crea tabla de contadores con unicidad/índice.0011–0015 siguen pendientes habituales. No usar --fake.

Procedimiento del operador, **no ejecutado en la base habitual**:

1. Revisar los cambios sin confirmar y empaquetar backend/frontend compatibles; confirmar servidor/base/ramas reales. Respaldar con pg_dump custom a ubicación privada y probar restauración en integración. Nunca versionar volcados o claves.
2. Cerrar registro/comercio y detener worker en la ventana de cambio. Conciliar `showmigrations websites`, `migrate --plan`, django_migrations y tablas/constraints. Si hay divergencias, detener aplicación sin falsear el historial.
3. Aplicar cadena solo al entorno autorizado, verificando dependencias: `python manage.py migrate --plan`, luego `python manage.py migrate` únicamente tras autorización para la base indicada. En esta intervención solo los runners desechables lo hicieron.
4. Desplegar código compatible después de la expansión de esquema, reiniciar procesos, ejecutar check y `python manage.py check_website_commerce --hostname <dominio>`. Este comando es READ ONLY y no realiza probes externos ni imprime secretos; no constituye aceptación.
5. Verificar P1/K0, login, empresa, catálogo laboral, cuentas y estadofalse. Revisar logs sin cuerpos/tokens, índices y constraints; no preparar A/B en datos habituales.

Rollback recomendado: ADMIN desmarca autorización con ETag actual; operador cierra registro y detiene worker. Confirmar P1/profilefalse, POST403 y conservación del historial/cancelación. Volver al código compatible conservando el esquema aditivo y evidencia. No revertir0011–0013 en una base con sesiones/consentimientos/solicitudes reales: eliminaría evidencia. Las reversiones físicas de0014/0015 se ensayaron solo en PostgreSQL desechable; no son un borrado productivo autorizado.

## SMTP/R2: checklist de aceptación real

SMTP: proveedor autorizado/remitente y DNS de envío; configurar WEBSITE_EMAIL_BACKEND=smtp, WEBSITE_EMAIL_FROM y WEBSITE_SMTP_HOST/PORT/USER/PASSWORD/TLS o SSL mediante almacén privado. WEBSITE_REGISTRATION_ENABLED continúa0 hasta aceptación. Configurar proxy CIDRs/límites, worker `send_website_emails` (dry-run sin --send), cuotas/alertas y `purge_website_registrations --website UUID` (dry-run sin --execute). Probar entrega a buzones autorizados, spam/rebotes, caducidad/reuso, errores/reintentos, recuperación solo cliente y apagado. No mostrar/verificar secretos mediante logs.

R2: R2_ACCOUNT_ID o R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME y R2_PUBLIC_BASE_URL de integración, prefijo persistente propio. Probar logo/banner desktop/mobile/foto/thumbnail, lectura CDN anónima, content-type, claves históricas y ownership A/B; fallos y limpieza de intentos huérfanos, sin borrar objetos de producción. Faltan credenciales/bucket autorizados; no hubo llamadas externas de escritura.

## Piloto Ferretería Tolentino y activación

Usar el Website/Company existentes que confirme el operador, sin crear otra empresa. ADMIN revisa lista pública, ProductPrice activos/moneda/impuestos/unidades y almacenes; CMS configura identidad/logo/banners/contacto/WhatsApp/SEO y publica. Seleccionar vínculos/destacados comerciales propios. Sin precio autorizado, mantener null; no copiar precios internos para llenar la tienda. Confirmar fotografía/alt y titularidad de dominio. No tocar datos fiscales/stock para preparar un recorrido.

Aprobar privacidad/versionado, plazos de altas pendientes y conservación de User/consentimientos/solicitudes; configurar revisión Customer sin apropiación por coincidencias. Probar minorista y mayorista/revocación con usuarios autorizados, sin grants ERP implícitos. Registro y comercio se aceptan por separado.

Después de migraciones, pruebas reales externas y QA: revisar HTTPS, DEBUG=false, hosts/CORS explícitos, claves seguras y topología de proxy, junto con XSS/CSP y dependencias. Obtener autorización explícita del operador y realizar el cambio ADMIN con ETag en **un Website piloto**. Verificar contexto, gate efectivo, creación idempotente, historial/cancelación y ausencia de reserva. Medir errores409/429/503, cola/rebotes y carga. Ante incidente, desautorizar y cerrar registro/worker conservando evidencias. No se ejecutó esta activación habitual.

## QA visual y riesgos

La QA visual total sigue pendiente; no se declara aprobada por SSR200. Se intentó descubrir navegador en esta intervención: el inventario devolvió browsers vacío y «The browser access host is unavailable». No se realizaron inputs o interacciones visuales. El historial anterior de Computer Use además registra detención por no poder verificar URL de Chrome; no se eludió esa política. El bloqueo de navegador no impidió las pruebas backend/HTTP anteriores. Checklist manual para desktop1920px, tablet768px y móvil360px:

1. Home A/B: identidad, metadata, banner, categorías/destacados en la misma sección, cambio rápido de categoría, carga/error/reintento; sin salto a shop al usar pestañas.
2. Shop: búsqueda, categoría/marcas, orden/filtros, página2, detalle, foto/alt, unidad y precio cero/null; sin datos internos.
3. Anónimo: agregar con/sin precio, cantidades/quitar/recargar y continuar→login. Cuenta: incorporación explícita, otra cuenta/B sin carrito ajeno; recálculo y conflicto sin perder selección.
4. Correo de integración real: registro/aviso, fragmento y doble montaje en desarrollo, prueba caducada/usada, identidad existente/Customer pendiente, recuperación sin tocar empleados.
5. Consentir y preparar: referencia PREPARED, un reintento/misma referencia, abrir enlace solo por clic, no estado recibido; historial/cancelación/expiración y opt-out.
6. ADMIN/CMS/trabajador/mixto: menús y URLs según permisos, ETag en dos pestañas conservando formularios, cambio de empresa sin arrastrar privilegios.
7. Tab/Shift+Tab/Enter/Escape, foco visible y retorno en diálogos, labels/errores, zoom200%, reduced-motion, contraste/lector de pantalla y ausencia de overflow horizontal de página. Rails horizontales deliberados sí.

Bloqueantes de aceptación operativa: migraciones habituales no autorizadas/aplicadas; SMTP/R2 reales pendientes; privacidad/conservación y contenido/política de Tolentino sin aprobar; QA visual completa y revisión de seguridad/configuración. La base habitual todavía carece de lista pública. No se declara lista para producción.

Riesgos no bloqueantes para seguir probando en integración: warnings documentales OpenAPI heredados, aviso de baseline-browser-mapping, costo de consultas de readiness/ETag (medir antes de escalar), ventanas fijas de rate limit y entrega SMTP al menos una vez. La suite ERP global mantiene fallos heredados que se comparan por identificador; su aceptación general es responsabilidad de una remediación aparte.

## Archivos D5

Backend creados: commerce.py, registration_limits.py, comandos check_website_commerce.py, migraciones0014/0015 y tests test_commerce_activation.py/test_registration_delivery.py. Modificados: models.py, public_content.py, order_requests.py, registration.py, registration_mail.py; catalog/services.py/selectors.py; website_catalog/serializers.py/views.py; commercial_accounts/registration.py/views.py/orders.py; config/settings.py, `.env.example`; tests test_catalog.py/test_order_requests.py; auditoría y helper HTTP aislado.

Frontend modificados: public-website.mjs, commercialSession.mjs; WebsiteCatalogPanel, ProductPurchase; CommercialProvider/Shell/Cart, RegistrationFlow/Administration, OrderRequests, cuenta/page.js y ruta pública cart/page.js; tests website-public/commercial-http/storefront-http y continuidad. Creados d5-commerce-http.integration.mjs/d5-registration-http.integration.mjs. No nuevas dependencias, proyectos o autenticación paralela.

Las evidencias JSON no incluyen el contexto privado de credenciales/pruebas sintéticas. Los helpers eliminan su base/contexto al detenerse; la compilación habitual se restaura después de terminar integración. La implementación permanece sin commit para revisión.

### Reproducción aislada

Con PostgreSQL local autorizado para crear bases desechables, desde backend:

```powershell
.venv/Scripts/python.exe docs/architecture/website-integration/run_catalog_security_checks.py --run-isolated . ../.tools/d5-postgresql.json apps.websites apps.inventory.tests.test_catalog_api apps.inventory.tests.test_catalog_security apps.inventory.tests.test_product_images
.venv/Scripts/python.exe docs/architecture/website-integration/run_catalog_security_checks.py --run-isolated . ../.tools/d5-full-regression.json apps
.venv/Scripts/python.exe docs/architecture/website-integration/run_storefront_integration.py --serve-isolated
```

En una consola de frontend, establecer únicamente para el proceso NEXT_PUBLIC_API_V1_URL y WEBSITE_API_V1_URL a http://127.0.0.1:8770/api/v1; compilar y arrancar `npm.cmd run start -- --hostname 127.0.0.1 --port 8771`. Ejecutar Node tests/*.test.mjs, commercial-http.integration.mjs, commercial-cart-http.integration.mjs before y storefront-http.integration.mjs. En stdin del helper enviar JSON `{"operation":"prepare_commerce"}`: aprovisiona exclusivamente el Website A sintético con contacto/aviso de fixture y usa el servicio ADMIN de opt-in. Ejecutar d5-commerce-http.integration.mjs active; enviar `{"operation":"price","amount":"12.00"}`; ejecutar el mismo script changed y disabled. No usar el contexto privado de credenciales fuera de estos scripts.

Detener helper con `{"operation":"stop"}`; para registro repetirlo con `--serve-isolated --simulate-email` (la simulación externa queda explícita). Preparar comercio mediante el mismo comando stdin; ejecutar d5-registration-http.integration.mjs start, enviar `{"operation":"deliver_email"}`, ejecutar complete; enviar `{"operation":"advance_registration_cooldown"}`, ejecutar recovery-start, deliver_email y recovery-complete. Esa opción usa locmem solo en el adaptador SMTP, no un proveedor real. Cada script valida el nombre exacto de la base y el contexto antes de operar. El helper retira la prueba privada de correo y la base al terminar.

Al finalizar, detener los procesos propios8770/8771, retirar contextos temporales y recompilar sin variables de integración. No ejecutar estos helpers para crear fixtures en apudig_mvp o producción; no son comandos de activación del piloto.
