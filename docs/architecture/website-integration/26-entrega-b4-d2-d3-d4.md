# B4-D2, D3 y preparación de D4

Continuación20/11/2026: [27-entrega-b4-d5.md](27-entrega-b4-d5.md) implementa opt-in persistente, integración de capacidades y solicitudes con activación exclusivamente sintética. El registro/comercio habitual siguen apagados. Este documento conserva los resultados históricos de D2–D4.

19/11/2026, America/Lima. Continúa el informe25. **Código de registro y revisión de carrito implementado; solicitudes preparadas con creación HTTP bloqueada. B4 no está aceptada ni activada.** Registro público, comercio y WhatsApp operativo permanecen apagados.

## Entorno conservado

Backend `websites_backend@a6ac628`; frontend `mvp_website@ce91c0c`. Se preservó el trabajo sin confirmar de D1. No se cambiaron ramas, `.env`, credenciales, `.gitignore`, DNS, objetos R2, datos habituales, commits o despliegues. La rama backend real difiere de develop; no se cambió automáticamente.

PostgreSQL local18.1, base habitual `apudig_mvp`, inspeccionada en transacción READ ONLY. Historial consistente;0011,0012 y0013 pendientes. `demo.localhost` continúa ACTIVE/verificado, Website publicado, revisión editorial26,21 vínculos comerciales/20 publicados, dos almacenes autorizados y **sin lista pública predeterminada**. Se observaron estos datos ya existentes, sin aprovisionarlos o atribuir sus cambios al agente. No se inventó un precio alternativo. Auditorías: `b4d23-local-environment.json` y `b4d234-local-environment-final.json`.

0011 de D1 se conservó. Nuevas0012 y0013 se aplicaron únicamente al crear bases desechables PostgreSQL, nunca a la habitual. No se utilizó SQLite ni `--fake`.

## D2: identidad, consentimiento y Customer

Se prepararon `WebsitePrivacyNotice` inmutable/versionado, `WebsiteRegistrationPolicy`, `CommercialRegistration`, `CommercialConsent` y `WebsiteEmailOutbox`. **No se creó un aviso, una política o un plazo real**: el usuario confirmó que siguen pendientes. La interfaz administrativa empieza con texto/version/plazo vacíos; no habilita registros.

Decisión autorizada: tras demostrar control del correo, crear un Customer mínimo mediante el servicio ERP existente solo si no hay coincidencias en la empresa. La coincidencia de correo o nombre es una señal de revisión, nunca autorización para adjudicar una ficha. El modo NEW_OR_REVIEW se selecciona explícitamente al configurar la política; el modelo conserva REVIEW_ALL como valor conservador. No se duplican maestros ni se cambian datos fiscales de fichas coincidentes. Un ADMIN debe seleccionar explícitamente un Customer propio y activo para resolver una revisión. CMS y personal básico no pueden hacerlo. Mayorista sigue requiriendo aprobación separada del ADMIN, no la obtiene por registrarse.

La solicitud inicial no busca User, no crea contraseñas ni cuentas y responde de forma uniforme para identidades conocidas/desconocidas. Se aplica enfriamiento por correo/Website y throttle por IP real/hostname. Una identidad User existente requiere además iniciar sesión con sus credenciales actuales: la prueba de correo no cambia su contraseña, nombre o membresías. Emails equivalentes ambiguos requieren revisión. El alta no crea UserCompanyAccess, UserRole o UserStore.

La recuperación comercial solo admite una identidad exclusivamente cliente, con vínculo vigente y prueba válida. Staff, superusuarios e identidades con membresía/rol/sucursal laboral deben usar el procedimiento central; esta ruta no restablece sus credenciales. Cambiar la contraseña revoca las sesiones comerciales del usuario.

### Correo preparado, entrega real pendiente

Se usa SMTP explícito con TLS o SSL, timeout y cola persistida. No existe fallback de consola/locmem como verificación real. La cola guarda únicamente hash SHA256 del secreto, estado/intentos y nombre saneado de la excepción; no guarda el token o cuerpo del correo. El secreto aleatorio solo existe en memoria durante el envío. Caduca en30 minutos, se consume una vez y se limita al Website, finalidad y aviso vigente. Hasta tres intentos, separación mínima de un minuto; recuperación de envíos atascados tras15 minutos. Esos plazos son técnicos, no una política legal de conservación.

El enlace usa el hostname registrado y el secreto en fragmento; Next retira el fragmento sin persistirlo ni enviarlo al SSR. Un origen local de pruebas solo es admisible con DEBUG, hostname `.localhost` coincidente y formato estricto. En producción se ignora ese override.

Variables nuevas documentadas en backend `.env.example`: WEBSITE_REGISTRATION_ENABLED=0, WEBSITE_EMAIL_BACKEND=disabled, WEBSITE_EMAIL_FROM, WEBSITE_SMTP_HOST/PORT/USER/PASSWORD/USE_TLS/USE_SSL y WEBSITE_EMAIL_DEV_ORIGIN. Los secretos y el remitente siguen vacíos; no se modificó `.env`. No hacen falta variables públicas con secretos en Next.

Comandos preparados, **no ejecutados con envío o borrado real**:

```powershell
.venv/Scripts/python.exe manage.py send_website_emails
# Solo cuando exista proveedor autorizado y aceptación real:
.venv/Scripts/python.exe manage.py send_website_emails --send --limit 20
.venv/Scripts/python.exe manage.py purge_website_registrations --website <UUID>
# --execute aplica la purga; sin él solo cuenta candidatos.
```

La purga usa el plazo del aviso aceptado y elimina solicitudes de registro y su outbox; no elimina User, Customer, cuentas activas o consentimiento global. La conservación de identidades, consentimientos y solicitudes comerciales necesita política propia antes del piloto.

## D3: oferta calculada por APUDIG

`/cuenta/carrito` reutiliza CartProvider, tarjetas, selector de presentaciones y componentes existentes. Permite una selección privada y revisión de oferta para cuentas verificadas; no activa el carrito público. El almacenamiento se separa por Website y CommercialAccount, sin importar ni sobrescribir carritos antiguos compartidos. Un perfil sin accountId falla de forma cerrada.

La API reutiliza `recalculate_commercial_cart`: producto/unidad publicados y propios, cantidades enteras, demanda conjunta, política de listas/impuestos/moneda y almacenes autorizados. El precio personalizado depende de la aprobación y perfil actual, no de claims obsoletos. No se aceptan precios, factores, Customer, Company o almacenes enviados por el cliente. Sin oferta autorizada no se inventa precio ni se toma compra como fallback. Precio cero válido conserva su significado.

La confirmación compara una huella de oferta con un recálculo actual. Precio/stock/condiciones cambiados devuelven409; Next conserva la selección y exige recalcular. Confirmar no fija precios futuros, reserva inventario ni crea una SalesQuotation. La huella comercial no sustituye ni depende del ETag editorial.

## D4: motor preparado y acceso cerrado

`CommercialOrderRequest` conserva titular/Website/Customer, referencia UUID, aviso aceptado, oferta comercial calculada, destino del snapshot publicado, revisión editorial y expiración técnica de15 minutos. Unicidad de Idempotency-Key por Website/cuenta; reintentos iguales reutilizan el registro y cuerpos distintos devuelven409. El reintento también revalida la oferta, Customer, estado, destino y revisión: no recupera un enlace vencido o incompatible. No se copian precios al CMS.

La preparación requiere cuenta vigente, confirmación expresa de compartir, recibo del aviso vigente y oferta recalculada. Historial/detalle/cancelación son exclusivamente del titular y Customer actuales; reenlazar un Customer no entrega el historial anterior. Estados disponibles: PREPARED, CANCELLED y EXPIRED derivado al leer; GET no modifica estados. Se auditan preparación y cancelación. No se implementó recepción/aceptación administrativa ni conversión a pedido ERP.

El destino WhatsApp procede de la revisión CMS publicada; no del navegador. El enlace incluye referencia y líneas comerciales, sin teléfono/correo del cliente ni observaciones privadas. Solo se entrega cuando el comercio autorizado lo permita, la solicitud esté vigente y exista consentimiento de compartir; requiere clic explícito. Abrir WhatsApp **no marca RECEIVED ni demuestra envío o recepción**.

**Situación efectiva: POST de creación devuelve403 COMMERCE_DISABLED, sin escrituras.** La capacidad se consulta en la única fuente pública commerceEnabled, que sigue devolviendo false. El motor de persistencia y formato de enlace se probaron directamente con fixtures aislados; no se presenta eso como flujo HTTP operativo de pedidos o integración WhatsApp real. Historial y cancelación están preparados; en el entorno HTTP sintético sin solicitudes, el historial devuelve vacío.

La interfaz futura de preparación solo aparece si coinciden las capacidades reales del perfil y de la oferta. Actualmente no aparece. `/cuenta/solicitudes` ya consulta historial propio; no muestra solicitudes ficticias.

## Contratos

Prefijo `/api/v1/`, slash final, JSON/no-store. H representa hostname activo/verificado con Website/Company publicados/activos; W el UUID descubierto y autorizado. No se admite company_id público como autorización. `b4d234-contracts.json` exporta17 rutas comerciales, incluidas las conservadas de D1, y componentes referenciados. El esquema ERP global conserva errores históricos: esta exportación no equivale a aprobación de todo OpenAPI.

| Método/ruta | Autorización y cuerpo principal |
| --- | --- |
| GET `storefront/sites/H/registration-policy/` | Anónimo; devuelve registrationEnabled=false y notice=null con registro cerrado |
| POST `storefront/sites/H/registrations/` | `{email,name,noticeVersion,consent,purpose}`;202 uniforme si habilitado; hoy503 |
| POST `storefront/sites/H/registrations/complete/` | `{token,password,purpose}` y JWT de identidad existente cuando corresponda; prueba de correo por sí sola no adjudica identidades |
| GET/POST `websites/W/registration-policy/` | ADMIN de empresa/superusuario; `{version,text,pendingRetentionDays,linkingMode}`, If-Match al escribir |
| GET `websites/W/registrations/` | Revisiones propias, paginación/búsqueda; ADMIN |
| POST `websites/W/registrations/{id}/review/` | ADMIN; `{customerId}` propio seleccionado explícitamente |
| GET `websites/W/registration-customer-options/` | Opciones de Customer propias/activas y acotadas; ADMIN |
| POST `storefront/sites/H/account/cart/quote/` | JWT comercial; `{items:[{productId,unitId,quantity}]}` |
| POST `storefront/sites/H/account/cart/confirm/` | Igual más `offerFingerprint`;409 si cambió |
| GET/POST `storefront/sites/H/account/privacy/` | Propietario; POST `{noticeVersion,accepted:true}`;503 sin aviso |
| GET/POST `storefront/sites/H/account/order-requests/` | Propietario; GET paginado. POST exige Idempotency-Key UUID y `{items,offerFingerprint,note,shareConfirmed:true}`, además del gate comercial; hoy403 |
| GET `storefront/sites/H/account/order-requests/{id}/` | Propietario actual;404 ajeno |
| POST `storefront/sites/H/account/order-requests/{id}/cancel/` | Propietario, cuerpo vacío; no admite marcar recibido |

Quote/confirm conservan huella, total/moneda/líneas, confirmed y ordersEnabled. Perfil D1 añade accountId para aislamiento local y deriva prepareOrders de la fuente comercial, hoyfalse. El aviso administrativo tiene ETag y responde428 sin precondición/412 obsoleta. Errores conservan status/code/fields;400 validación,401 sesión,403 permiso/gate,404 ajeno,409 prueba/oferta/aviso/idempotencia,429 límite,503 infraestructura/esquema/proveedor. La UI no elimina formularios ante412 ni carritos ante409.

## Archivos

Backend nuevos: `apps/websites/registration.py`, `registration_mail.py`, `order_requests.py`; migraciones0012/0013; comandos send_website_emails/purge_website_registrations; tests test_registration/test_cart_api/test_order_requests; `apps/api/v1/commercial_accounts/registration.py`, `quotation.py`, `orders.py`.

Backend modificados sobre D1: models, settings, `.env.example`, commercial_accounts urls/views/serializers, helper aislado y esta documentación. Los cambios previos de tokens/autenticación/usuarios/D1 no se sobrescribieron.

Frontend nuevos: `services/commercialRegistration.mjs`; `components/account/RegistrationFlow.jsx`, `RegistrationAdministration.jsx`, `CommercialCart.jsx`, `OrderRequests.jsx`; rutas registro/verificar-cuenta/recuperar-cuenta/cuenta/carrito; tests commercial-registration y commercial-cart-http. Modificados: commercialSession, CommercialProvider/Shell, panel de cuentas y solicitudes, CartProvider/CartDrawer/ProductCard, tests commercial-session y continuidad. Se reutilizan dashboard, login y UI; sin dependencias nuevas ni cambios a inventario/ventas/POS.

## Verificación y límites

- PostgreSQL18.1: **253 pruebas acotadas correctas**,17 nuevas de registro,4 de API de oferta y6 de solicitudes, además del alcance D1. Bases `test_apudig_catalog_p0_tests`, recreadas/eliminadas por runner. Evidencia `b4d234-postgresql.json`.
- Suite ERP completa:794 pruebas,79 failures/36 errors. La comparación por identificador con HEAD limpio752 y D1 con767 conserva exactamente los mismos115 casos fallidos, sin nuevos. Ver `b4d234-full-regression.json` y `b4d234-regression-comparison.json`. No se declara aprobada la suite global por conservar fallos heredados.
-81 tests Node correctos (`node --test tests/*.test.mjs`), lint correcto. No existe script npm test: se usa Node directamente. Build aislado y build final con configuración habitual correctos. Aviso conocido baseline-browser-mapping antiguo; no se instalaron dependencias para ocultarlo.
-16 checks HTTP reales:10 D1 y6 D2/D3/D4, Next8771→Django8770→PostgreSQL `test_apudig_b4c_http`. Correo sintético verificado solo como fixture; ningún envío externo. Registro503, creación403 sin nuevas solicitudes, historial vacío y aviso503 sin configurar. SSR de cuatro nuevas rutas sin datos privados de cuenta. Cambio de precio70.80→84.96 invalida confirmación anterior, conserva revisión CMS y permite nuevo recálculo. Evidencias `b4d234-session-http.json`, `b4d234-http-before.json`, `b4d234-http-after.json`.
- Las pruebas D2 simulan **únicamente el adaptador SMTP externo** con locmem; prueban PostgreSQL, hashes, expiración, identidad existente, revisión, recuperación, purga y errores. No demuestran entrega real. D4 prueba persistencia/idempotencia en motor con fixtures y API cerrada, no creación pública operativa.
- Django check correcto, makemigrations --check --dry-run sin diferencias. Migraciones aplicadas solo en bases aisladas. Procesos8770/8771 terminados, contexto privado sintético eliminado y build habitual restaurado. No se detuvieron procesos habituales del usuario.

### Visual, SMTP y R2

QA visual D2–D4 **no ejecutada en este turno ni aprobada**. D1 registró que Computer Use no pudo verificar la URL de Chrome y detuvo la navegación; no se usó HTTP como sustituto de validación visual. Falta revisar en navegador real360px/768px/escritorio, teclado, foco/labels, errores y persistencia tras recargar.

Checklist manual sobre entorno aislado autorizado:

1. Abrir registro/verificación/recuperación en A y B: aviso de registro cerrado, sin recopilar datos; hostname desconocido404. Verificar noindex y ausencia de contactos privados en HTML.
2. Entrar con cliente sintético A: cuenta/carrito sin enlaces de personal; buscar, elegir presentación, agregar/quitar/cambiar cantidad y recargar. Otra cuenta o B no recupera su selección.
3. Recalcular, cambiar precio/stock desde fixture y confirmar:409 legible, selección conservada, recálculo explícito. Sin botones de pedido/WhatsApp con capacidades falsas.
4. Solicitudes: historial vacío real, estados de carga/error, expiración/cancelación con fixtures autorizados. Nunca recibido por clic.
5. ADMIN: aviso inicialmente vacío, escribir solo texto legal aprobado, probar428/412 en dos pestañas preservando formulario; revisión manual propia. CMS y usuario laboral básico sin esas vistas ni acceso API.
6. Tab/Shift+Tab/Enter/Escape, menús y formularios sin desbordes, contraste, mensajes de error y lectura con asistencia. No marcar responsive/accesibilidad aprobados sin ejecución.

SMTP real no disponible: registrofalse, email backend disabled, proveedor no configurado. R2/CDN no probado: solo existe URL pública, faltan cuenta/credenciales/bucket y no hay registros WebsiteMedia activos. Se mantuvo la autorización previa de simular servicios externos; no se subieron objetos productivos.

## D5: pendientes exactos antes de activar

1. Revisar respaldo, grafo y despliegue compatible de0011–0013 en integración autorizada antes de decidir su aplicación habitual. No auto-migrar al arrancar procesos.
2. Aprobar texto/versionado de privacidad, conservación de altas pendientes y política para identidades/consentimientos/solicitudes. Configurarlos por ADMIN; no inventar textos legales. Conciliar correos equivalentes existentes.
3. Elegir/configurar proveedor; entregar correo real a buzones autorizados, caducidad/reintentos/errores, recuperación exclusivamente cliente y observabilidad sin secretos. Configurar worker y purga. Límites compartidos/cache, IP del proxy confiable y cuotas del proveedor antes del registro público; locmem por proceso no es protección distribuida suficiente.
4. Validar R2/CDN autorizado, carga/lectura anónima/limpieza y claves históricas. Completar QA visual y flujo integral de registro/aviso/cuenta/carrito/solicitud en dos empresas.
5. Implementar el **único opt-in comercial persistente, defaultFalse y auditado** en WebsiteCatalogSettings, con autorización ADMIN, precondiciones y bloqueo Website coherente con creación. No existe todavía un interruptor aceptado que pueda activarse. P1 sigue devolviendo false; el lector público Next actualmente rechaza true: hay que adaptar ambos contratos y sus pruebas en D5, no basta cambiar una variable.
6. Conciliar datos del piloto: lista autorizada, moneda/impuestos/unidades, almacenes, Customer y teléfono publicado. La base habitual observada carece de lista pública predeterminada; no suplirla con costos o listas internas.
7. Acordar recepción/aceptación administrativa y retención de solicitudes antes de ampliar estados o convertirlas en operaciones ERP. Este código no registra pedidos recibidos ni reservas.
8. Investigar y remediar los fallos ERP heredados por alcance propio; conservar la comparación diferencial. Revisión XSS del almacenamiento actual y límites del login común siguen como riesgos de piloto de D1.

Hasta completar y revisar esa aceptación: registro deshabilitado, comercio false, POST de solicitudes bloqueado y ninguna venta, pedido, reserva o mensaje real generado.
