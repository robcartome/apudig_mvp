# B4-D1 — Sesión y dashboard comercial

Continuación posterior: [26-entrega-b4-d2-d3-d4.md](26-entrega-b4-d2-d3-d4.md). Describe el código de registro/revisión de oferta y motor de solicitudes preparado; registro y comercio siguen cerrados. Este informe conserva el resultado histórico de D1.

19/11/2026, America/Lima. **D1 implementada y validada por pruebas automatizadas/HTTP; aceptación visual pendiente.** Continúa20–24. Registro público, commerceEnabled, pedidos y WhatsApp operativo siguen deshabilitados. D2, D3 y D4 no se iniciaron simultáneamente: quedan ordenadas al final de este informe.

## Entorno y límites

Bases limpias iniciales: backend `websites_backend@a6ac628`, frontend `mvp_website@ce91c0c`. No se cambiaron ramas, credenciales, `.env`, `.gitignore`, datos habituales, commits o despliegues.

Auditoría READ ONLY de PostgreSQL local18.1 `apudig_mvp`:0010 ya estaba aplicada al iniciar esta intervención, por un cambio previo del entorno; esta intervención no la aplicó. Historial consistente, dominio demo.localhost activo/verificado y Website publicado en revisión17. Sin productos publicados, política comercial o medios Website. Nueva0011 pendiente en la base habitual; solo se aplicó en bases desechables. Ver `b4d1-local-environment.json`.

La auditoría final `b4d1-local-environment-final.json` observa un cambio concurrente de datos habituales: revisión18, tres WebsiteProduct (uno publicado), política con lista predeterminada y un almacén autorizado. Esta intervención no realizó esas escrituras ni les atribuye autoría; se conservaron.0011 sigue pendiente, R2 sin credenciales y medios Website en0. Los resultados de integración son independientes de ese cambio porque sus fixtures utilizaron exclusivamente bases desechables verificadas por nombre.

## Sesión y separación de finalidades

Se reutilizan User, sus credenciales Django, build_token/decode_token, clave JWT y TTL existentes. No se crea otra identidad ni otro motor de contraseñas. `POST /api/v1/auth/token/` admite `context="commercial"` y `hostname`; sin context mantiene la respuesta laboral anterior, con companies y selección de empresa. Un cliente sin membresía laboral recibe su sesión comercial válida, sin crear UserCompanyAccess, UserRole o UserStore.

El token comercial contiene únicamente sub, purpose=commercial, session_id, hostname, website_id, type, iat y exp. No lleva Company laboral, sucursal, roles, permisos o aprobación mayorista como autoridad. `CommercialSession` persiste revocación, vigencia, vínculo/Website/Customer, prueba de contacto de emisión y hash de autenticación de Django. No almacena el JWT ni una contraseña en claro.

Cada operación protegida comprueba firma/tipo/expiración/finalidad y consulta sesión, User activo, hostname registrado activo/verificado, Website publicado, Company activa, CommercialAccount vigente, Customer activo/propio y correo verificado. Relacionar la cuenta a otro Customer o renovar su prueba de contacto invalida el contexto anterior; cambios de contraseña/perfil se vuelven a verificar. Los derechos mayoristas se leen desde la cuenta actual, no desde claims permanentes.

`JWTAuthentication` laboral rechaza purpose=commercial antes de evaluar permisos o superusuario. Sus subclases CMS/catálogos heredan esa restricción. El refresh comercial mantiene finalidad/hostname/Website y revalida el vínculo; no puede pasar por el constructor de refresh laboral. Logout comercial revoca en servidor tanto acceso como refresh mediante la sesión persistida, incluso si el vínculo ya fue suspendido. No se modifica la semántica laboral heredada de logout (stateless); su posible revocación general requiere una remediación aparte, no debe confundirse con la garantía comercial nueva.

Un usuario mixto entra explícitamente desde su identidad APUDIG o sus mismas credenciales. El intercambio revalida la cuenta destino; no reutiliza el contexto laboral como autorización comercial. Puede mantener su sesión de personal por separado y volver a ella mediante un enlace explícito. No se permite convertir un JWT comercial en JWT laboral: para otro acceso laboral se utiliza su sesión laboral existente o el login normal.

### Transporte de Next

Las credenciales van al endpoint existente; los tokens comerciales usan una clave local por Website distinta de las claves laborales. localStorage ya es el transporte administrativo del proyecto; D1 conserva esa decisión y no lo presenta como protección contra XSS. No hay cookies de dominio amplio, tokens en URLs, SSO entre dominios ni redirecciones libres. Otro dominio requiere su propia sesión por origen. Si el navegador no permite persistencia, la sesión queda en memoria durante la visita.

Las llamadas comerciales envían Bearer, credentials=omit y cache=no-store. No aceptan cookies de sesión Django como identidad comercial; por tanto no utilizan autenticación por cookie sin CSRF. CORS conserva la allowlist existente; en integración se autorizaron solo los orígenes locales de prueba dentro del proceso. No se habilitaron wildcard, cookies cruzadas o configuraciones productivas.

El refresh del cliente comercial no llama a select-company ni modifica el almacenamiento laboral. Un fallo de logout no se presenta como cierre exitoso: permite reintentar. Los errores HTTP conservan status/code/fields; el guard borra la vista protegida al fallar una comprobación y revalida al recuperar el foco. La autorización definitiva sigue en cada petición Django.

## Contratos implementados

Base `/api/v1/`, JSON, slash final. Respuestas privadas no-store. Los servicios comerciales no crean usuarios, clientes, Websites o membresías al leer o iniciar sesión.

| Operación | Contrato / autorización |
| --- | --- |
| POST `auth/token/` |Credenciales existentes. Para cliente: `{email,password,context:"commercial",hostname}`. Devuelve context, websiteId, access/access_token y refresh/refresh_token. Sin contexto conserva login laboral |
| POST `auth/refresh/` |`{refresh_token,hostname}` para sesión comercial. También conserva alias refresh. Devuelve access/access_token, context y websiteId; no cambia finalidad |
| POST `auth/logout/` |`{refresh_token}` comercial revoca la sesión,204 idempotente. La API no exige un access vigente para revocar |
| POST `storefront/sites/{hostname}/account/session/` |Body vacío; Bearer de identidad laboral existente o sesión comercial vigente. Emite una nueva sesión solo si el titular tiene cuenta verificada en el Website destino |
| GET `storefront/sites/{hostname}/account/` |Exclusivamente Bearer comercial del hostname/Website. Sin query de Customer/empresa. Perfil del titular; PATCH no implementado |
| GET `websites/{websiteId}/commercial-accounts/` |Solo ADMIN de empresa/superusuario con membresía/contexto actuales. search, limit1–100 (24 por defecto), offset; lista paginada propia |
| GET `websites/{websiteId}/commercial-accounts/{accountId}/` |Misma autorización,404 para cuenta ajena. Devuelve ETag fuerte de cuenta |
| PATCH `websites/{websiteId}/commercial-accounts/{accountId}/` |Únicamente `{wholesaleApproved: boolean}` estricto; If-Match obligatorio428, obsoleto412. No permite cambiar Customer, estado, correo o lista. Reutiliza servicio de aprobación, validación de lista y AuditLog |

Perfil comercial: `{context,websiteId,company:{name},user:{name,email,phone},contactVerified,verificationChannel:"email",wholesaleApproved,capabilities:{catalog:true,prepareOrders:false,registration:false}}`. No devuelve Customer fiscal, notas, documentos, roles/permisos laborales, proveedores, costos, almacenes, stock exacto o listas internas. La marca de verificación corresponde al correo; no acredita control del teléfono.

Fila administrativa: `{id,status,etag,user:{name,email},customer:{id,name},contactVerified,wholesaleApproved,priceList:{id,name,active}|null}`. Solo retorna lista de la misma empresa y perfil comercial activo. Cada fila lleva su propia precondición; el PATCH retorna ETag actualizado. Roles CMS sin ADMIN no consultan ni aprueban cuentas. La asignación de una lista al Customer continúa siendo responsabilidad ERP; D1 solo la consulta y no duplica ese maestro.

Esquema acotado exportado: `b4d1-contracts.json` contiene los contratos comerciales y login/refresh/logout, sus componentes y finalidades Bearer. Las rutas nuevas tienen anotaciones explícitas; no se presenta como una aprobación del esquema ERP global, que conserva errores históricos de documentación.

## Interfaz

- `/cuenta`: bienvenida, empresa, verificación de correo y aprobación mayorista actuales, acceso al catálogo y perfil. No presenta una lista personalizada de precios: eso corresponde a D3.
- `/cuenta/perfil`: lectura de nombre, correo y teléfono del propio User. No permite editar datos fiscales del Customer ni cambiar contactos sin reverificación.
- `/cuenta/solicitudes`: estado explícito de funcionalidad no habilitada; sin datos ficticios o llamadas a un backend inexistente.
- `/admin/cuentas-comerciales`: sección del dashboard existente para ADMIN de empresa/superusuario; búsqueda, paginación, consulta de estado/lista, aprobación/revocación y recarga explícita ante412/428. Cambiar empresa remonta el panel y evita conservar cuentas/permisos de la anterior.
- Website público: acceso «Mi cuenta» en header y menú móvil. No es un enlace de registro ni activa carrito.

Se extrajo `DashboardFrame` del contenedor administrativo existente y se reutiliza en `/admin` y `/cuenta`; no se creó otro dashboard independiente. Los guards, menús y sesiones comerciales están separados. Se reutilizan Card, Button, Input, Label y LoadingIndicator existentes. `CredentialsForm` es compartido con el login laboral; no se agregaron dependencias. Preview CMS conserva su exclusión del marco administrativo.

## Pruebas y evidencia

-15 pruebas nuevas de sesión/contrato PostgreSQL;226 Website/catálogos/imágenes acotadas correctas.
-767 pruebas ERP completas:79 failures/36 errors. No se comparó ciegamente con el informe histórico de113: aparecieron dos diferencias y se volvió a ejecutar HEAD a6ac628 en un snapshot aislado, sin checkout o modificaciones de ramas. Baseline actual752: exactamente79 failures/36 errors, **cero nuevos casos fallidos**. Global no aprobada. Ver `b4d1-current-baseline.json`, `b4d1-full-regression.json`, `b4d1-regression-comparison.json`.
-Los dos casos adicionales respecto al informe antiguo se reproducen sin D1: filtro diario de cierres POS y reversión de salida de inventario en ventas (la segunda rechaza una fecha con operaciones posteriores). No se atribuyó una causa temporal definitiva ni se alteraron módulos ERP para ocultarlos.
-75 pruebas Node correctas, incluidas6 nuevas de transporte/almacenamiento/refresh/logout y precondiciones administrativas. Lint y build correctos, también build aislado y restauración final sin overrides. Aviso conocido de baseline-browser-mapping antiguo; sin instalar dependencias para silenciarlo.
-10 comprobaciones HTTP reales en Next8771→Django8770→PostgreSQL18.1: cuenta sin membresía, A/B, rechazo ERP/CMS, refresh, aprobación/revocación en vivo,412, compatibilidad laboral, CORS allowlist, logout en servidor, SSR sin PII/JWT y comercio apagado. Ver `b4d1-http.json`. Las pruebas Node unitarias usan respuestas simuladas; este flujo HTTP no las utiliza.
-`manage.py check` correcto, `makemigrations --check --dry-run` sin cambios, grafo consistente. La migración0011 se ejecutó al crear las bases desechables, no en `apudig_mvp`.

Los fixtures contienen dos Companies, Websites y Customers propios; un cliente comercial A/B sin membresías laborales y un trabajador con cuenta comercial. Las pruebas Django cubren además cuenta no verificada, suspendida/revocada, UUID ajeno, contexto sin empresa, JWT expirado, sesión expirada, cookies sin Bearer y perfiles sin campos privados. Se marcaron/verificaron pruebas de correo **exclusivamente como fixture sintético**, sin afirmar entrega real por email.

### QA visual pendiente

Se aplicó la habilidad computer-use para seleccionar Chrome. Antes de navegar, la herramienta detuvo Computer Use al no poder determinar la URL del navegador con suficiente confianza para aplicar su política. No se eludió el bloqueo ni se continuó con inputs de navegador. **No hay aprobación visual de D1**, ni evidencia de login comercial por UI en esta entrega. El éxito HTTP no sustituye esa revisión.

Checklist manual sobre integración autorizada, en escritorio, tablet y móvil:

1. Abrir A/cuenta sin sesión; verificar formulario, labels/foco, aviso de registro deshabilitado y enlace de regreso. Tab, Shift+Tab, Enter y mostrar/ocultar contraseña.
2. Entrar con cliente sintético sin empresa laboral; comprobar bienvenida, empresaA, correo verificado y ausencia de menús CMS/catálogos laborales. Perfil sin datos fiscales; solicitudes con aviso pendiente.
3. Recargar/foco y renovar sesión; abrir B en otra sesión de navegador e iniciar sesión allí sin transportar tokens. No debe mostrar A. Dominio desconocido404.
4. Cliente mixto: desde sesión laboral entrar explícitamente en cuenta y volver a personal. Cerrar cliente debe dejar separada la sesión laboral y rechazar el JWT comercial anterior en API.
5. ADMIN: cuentas propias, búsqueda/paginación, lista asignada, aprobar y revocar. CMS/trabajador: sin acceso, incluso por URL directa. Dos pestañas provocan412 y conservan búsqueda/selección hasta recarga explícita.
6. Recorrido responsive sin overflow de página, menú lateral/overlay, Escape/foco, header con Mi cuenta, estados de carga/error y contactos largos. No aprobar contraste/lector de pantalla sin comprobarlos.

## Archivos y migraciones

Backend nuevos: `apps/websites/commercial_sessions.py`, `apps/websites/migrations/0011_commercial_sessions.py`, `apps/websites/tests/test_commercial_sessions.py`, paquete `apps/api/v1/commercial_accounts/` (authentication, serializers, views, urls, schema).

Backend modificados: `apps/websites/models.py`, `apps/websites/apps.py`, `apps/api/v1/authentication.py`, `apps/api/v1/auth/tokens.py`, `apps/api/v1/users/views.py`, `apps/api/v1/users/serializers.py`, `apps/api/v1/urls.py` y helper de integración sintética. No se cambió0010 ni migraciones históricas.

Frontend nuevos: `services/commercialSession.mjs`, `services/commercialAccountsRepository.mjs`, `components/account/*`, `components/auth/CredentialsForm.jsx`, `components/layout/DashboardFrame.jsx`, rutas `/cuenta*` y `/admin/cuentas-comerciales`, tests `commercial-session.test.mjs` y `commercial-http.integration.mjs`.

Frontend modificados: AdminLayout, Sidebar, StoreHeader, login y continuidad. `/catalog`, `/admin/catalog_admin`, `/shop` y `/admin/website` mantienen su responsabilidad y APIs.

## Uso y pendientes operativos

No se crean cuentas comerciales habituales para poder probar. El entorno habitual necesita revisión/aplicación autorizada de0011 antes de usar sesiones comerciales; iniciar sesión comercial con una cuenta existente y esquema de sesión pendiente devuelve503, sin auto-migrar. Reiniciar los procesos tras la aplicación que decida el operador.

Reproducción aislada: usar `run_storefront_integration.py --serve-isolated` en una consola interactiva (o PTY), luego compilar Next con NEXT_PUBLIC_API_V1_URL y WEBSITE_API_V1_URL apuntando a127.0.0.1:8770/api/v1, solo en el entorno del proceso. Arrancar Next en8771 y ejecutar `node tests/commercial-http.integration.mjs`. Stdin `{"operation":"stop"}` termina Django, elimina la base test_apudig_b4c_http y retira el contexto privado de credenciales sintéticas. No imprimir ni publicar ese contexto.

Al terminar se detuvieron8770/8771, se eliminaron las bases desechables mediante sus runners y se retiró el contexto sintético. Se restauró el build sin variables de integración. No se tocaron procesos habituales del usuario, DNS o almacenamiento R2.

Riesgos operativos heredados para piloto: logout laboral stateless, endurecimiento de límites del login común, conciliación de emails equivalentes antes del registro, revisión de XSS por transporte actual en almacenamiento de navegador, R2/CDN real, contenido/política comercial de la empresa piloto y QA visual pendiente. No se declaran resueltos por separar los JWT.

## Continuación ordenada

**D2 — Registro y correo:** conectar proveedor autorizado, límites/entrega/recuperación, consentimiento versionado y retención, vinculación Customer revisada sin apropiación por coincidencia de datos. Registro público debe continuar deshabilitado hasta pruebas reales. No hay dependencia de proveedor para los fixtures D1.

**D3 — Cotización y carrito:** exponer recálculo de24 únicamente con contexto comercial vigente, usar lista aprobada cuando corresponda, huella comercial de oferta, revisar cambios de precio/stock y confirmar resumen en Next. No confiar en precios o cantidades del navegador ni en ETag editorial para esta confirmación.

**D4 — Solicitudes y WhatsApp:** contrato/modelo persistido, referencia no enumerable, Idempotency-Key por titular/Website, expiración, historial propio y estados. Destino del snapshot CMS publicado; abrir el enlace no significa recibido. Sin ventas, reservas o SalesQuotation automáticos.

**D5 — Aceptación y activación:** revisar migraciones, correo, R2, QA, datos del piloto y único opt-in comercial defaultFalse auditado. Mantener comercio apagado hasta superar esa aceptación. Esta entrega no autoriza una activación implícita por tener cuenta o lista asignada.
