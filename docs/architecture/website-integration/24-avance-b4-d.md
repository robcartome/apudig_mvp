# B4-D: núcleo comercial y pendientes de integración

Continuación posterior: [25-entrega-b4-d1.md](25-entrega-b4-d1.md) implementa sesión/contexto comercial, `/cuenta`, perfil y administración mayorista. Las afirmaciones de ausencia de esas piezas en este informe describen la entrega inicial24, no el estado posterior. D2–D4 y activación siguen pendientes.

19/11/2026, America/Lima. **Entrega parcial de desarrollo; B4 no está completada ni aceptada para pedidos.** Continúa los documentos20–23. El usuario autorizó continuar B4 y confirmó: cualquier cliente registrado con contacto verificado podrá preparar solicitudes; la aprobación ADMIN es solo para mayoristas. Proveedor pendiente: **mantener registro público deshabilitado**. R2 real continúa pendiente por decisión previa; no se utilizaron credenciales productivas.

## Base y entorno

Backend `websites_backend@6163c1b`, frontend `mvp_website@07f367f`; ambos estaban limpios al iniciar. Se mantuvieron esas ramas (el checkout backend actual no es develop), sin checkout, merge, commit, push o despliegue. `.gitignore`, `.env` y credenciales preservados.

Auditorías inicial y final en transacción PostgreSQL READ ONLY, base local `apudig_mvp`, PostgreSQL18.1: historial consistente; `demo.localhost` ACTIVE/verificado, Website PUBLISHED, revisión17, empresa activa. No hay política comercial, WebsiteProduct publicados o medios Website. No se configuraron listas, almacenes, productos o contactos reales. Por ello `/shop` vacío sigue siendo correcto. La auditoría final registra únicamente la nueva0010 pendiente, **no aplicada a la base habitual**.

## Implementado

### Descubrimiento de sucursales

Se cerró el404 observado en23: `GET /api/v1/auth/store-access/stores/me/`. Consumidores: `AuthContext.selectCompany`, `StoreSelector` y el selector legado de series mediante `getMyStoresDetail`. Conserva `store_ids` y agrega `stores: [{id,name}]`, evitando consultas individuales a rutas de detalle inexistentes. No agrega operaciones para asignar usuarios o cambiar el contexto del JWT.

Reutiliza JWT y autorización actual del catálogo laboral, sin exigir permiso de productos: usuario activo, empresa activa, contexto válido y membresía vigente. ADMIN de empresa/superusuario ve sucursales activas propias; los demás requieren asignación UserStore activa y membresía compatible. Sin empresa no existe consulta global. Respuesta privada no-store. El frontend utiliza la ruta con slash final; se mantienen los demás contratos.

### Dominio de cuentas comerciales, todavía interno

`CommercialAccount`: vínculo único `(user, company)` con Customer canónico de la misma empresa; ACTIVE/SUSPENDED/REVOKED, prueba de correo y aprobación mayorista separadas. ACTIVE sin contacto verificado **no** permite acceso comercial. No crea UserCompanyAccess, roles o sucursales. No copia listas de precios al vínculo ni modifica Customer.

`CommercialEmailChallenge`: secreto aleatorio de256bits, almacenamiento SHA256, finalidad exclusiva de prueba de correo de esa cuenta, expiración30min y un solo uso. Se liga a cuenta/empresa/correo; emitirlo no verifica al usuario. Un enlace nuevo invalida anteriores y tiene cooldown de1min. El servicio devuelve el secreto únicamente al futuro adaptador interno de entrega; **no hay endpoint que lo entregue al navegador, envío simulado o proveedor configurado**. Estos límites son defaults técnicos internos, no una política de registro público aprobada.

Los selectores releen usuario, empresa, Customer, vínculo, prueba y aprobación. Cambiar el perfil/contraseña del usuario exige conservadoramente reverificar (comparación `User.updated_at` con la prueba), incluso si restaura el correo anterior. Los cambios directos de datos fuera de servicios siguen siendo operaciones privilegiadas; el futuro flujo de contacto debe centralizarlos. Suspender/revocar impide acceso aunque se conserve una referencia anterior en memoria.

Solo ADMIN de empresa/superusuario con contexto vigente puede autorizar/revocar mayoristas; se reutiliza autorización de política comercial y AuditLog. La lista procede de `SalesCustomerProfile`, activa, propia y autorizada. La cuenta básica utiliza oferta pública; una cuenta mayorista aprobada utiliza exclusivamente su lista asignada. Una lista inválida o un precio ausente no cae silenciosamente a otra lista. La aprobación no altera la oferta anónima K0/K1. CMS no recibe aprobación comercial implícita.

No están implementados el alta pública, la vinculación/revisión de clientes existentes, un contexto JWT comercial, pantallas de cuenta ni APIs administrativas de aprobación. Los servicios internos no sustituyen esas piezas.

### Recálculo de carrito en servidor

Servicio reutilizable `recalculate_cart`; variante `recalculate_commercial_cart` revalida la cuenta verificada y su lista vigente. Solo acepta `productId`, `unitId`, cantidad entera1–999, sin precios, factores, empresa o cliente enviados por navegador. Máximo200 líneas, conservando la capacidad previa: la propuesta histórica de50 no se aplica ni trunca carritos existentes.

Reutiliza resolución por hostname y ofertas ERP publicadas. Valida unidades activas/base, impuestos y moneda; cero es válido, null no permite un total engañoso. Una línea retirada/ajena/inválida rechaza todo el cálculo. Suma demanda en unidad base entre presentaciones del mismo producto y usa solo almacenes autorizados; sin configuración la disponibilidad es unknown. No publica, reserva o modifica stock, ventas ni SalesQuotation.

Resultado interno: websiteId, currency, priceIncludesTax, items[{productId,unitId,name,unit,quantity,unitPrice,total,availability}], total y offerFingerprint. No expone costos, proveedores, listas o cantidades exactas de stock. `confirm_cart_offer` recalcula oferta pública y rechaza una huella anterior con409 OFFER_CHANGED. La huella no reserva ni garantiza una operación futura: la preparación final deberá recalcular también la oferta comercial y sus permisos.

**No se creó todavía POST cart/quote/ u order-requests/**. Tampoco se generan referencias de pedido, estados PREPARED, historial o URL WhatsApp desde estos servicios. No presentar estos tests como una solicitud comercial E2E.

### Carrito Next preparado, deshabilitado en el Website real

Selecciones v2 por UUID Website + producto/unidad; solo persiste IDs, cantidad y observaciones de240caracteres. No persiste precios, stock o identidad como autoridad. Clave nueva separada del carrito demo v1: no importa, borra o sobrescribe el anterior. Error de formato/tenant/capacidad se informa y bloquea escritura automática del registro original, en lugar de truncarlo.

`CartProvider` utiliza esta variante en modo real; recupera detalles por IDs mediante K1 con concurrencia máxima4, independientemente de la página de productos. Un artículo retirado o cuyo detalle falle permanece marcado para revisión. Línea y acciones usan identidad producto/unidad; el drawer conserva ambas presentaciones. El detalle prepara selección de unidad, y los importes usan moneda del Website. Se conserva la variante demo explícita.

Todos estos controles reales permanecen condicionados a `commerceEnabled===true`; P1 sigue false. El provider no lee/escribe carrito real ni consulta sus productos mientras está deshabilitado. Se bloqueó expresamente el antiguo WhatsApp calculado en navegador para sitios reales: no podrá reactivarse accidentalmente con un futuro cambio de bandera. **La interfaz de confirmación y envío autenticado sigue pendiente**, no existe un pedido funcional todavía.

## Archivos

Backend nuevos: `apps/api/v1/users/store_access.py`, `apps/websites/accounts.py`, `apps/websites/catalog/quotation.py`, `apps/websites/migrations/0010_commercial_accounts_and_email_challenges.py`, tests `test_commercial_accounts.py`, `test_quotation.py`, `test_store_discovery.py`.

Backend modificados: `apps/api/v1/users/urls.py`, `apps/websites/models.py`, `apps/websites/catalog/selectors.py`. El helper `audit_local_website.py` acepta `--report nombre.json` para conservar baselines históricos. No cambian migraciones0001–0009 ni modelos ERP.

Frontend nuevos: `src/lib/commerce/website-cart.mjs`, `tests/website-cart.test.mjs`. Modificados: `CartProvider`, `CartItem`, `CartDrawer`, `CartPage`, `ProductCard`, `ProductUnitOffer`, `src/lib/commerce/cart.mjs`, `src/lib/storefront/store.js`, `src/services/storeAccessService.js` y continuidad.

## Verificaciones y límites

- `manage.py check`: correcto; `makemigrations --check --dry-run`: sin cambios; grafo consistente.
- Migración0010 aditiva creada y aplicada solo por el runner en PostgreSQL desechable `test_apudig_catalog_p0_tests`; sin fake ni alteración del historial existente. Unicidad verificada en PostgreSQL, no solo validación de modelo.
-211 pruebas Website/catálogos/imágenes correctas, incluidas25 nuevas (12 cuentas,9 cálculo,4 sucursales). Tras ajustes finales se repiten cuentas y cálculo por separado; evidencia `b4d-accounts-final.json` y `b4d-quotation-final.json`.
- Suite ERP752: mismos78 failures/35 errors que baseline727 de23; cero nuevos/resueltos por identidad de caso. **Global no aprobada**. La comparación completa precede el endurecimiento final de prueba de contacto/fingerprint; las suites enfocadas posteriores verifican esos cambios.
- Frontend lint y build correctos;69 pruebas Node correctas. El único aviso de herramienta es la antigüedad de baseline-browser-mapping; no se agregan dependencias para ocultarlo.
- Smoke HTTP habitual READ ONLY: Home/shop/admin/website/catalog/login/contact/catalog_admin200; localhost200; Host desconocido404; P1 revisión17/commercefalse; K0 vacío; catálogo laboral y descubrimiento de sucursales anónimos401. Un200 de una ruta SPA protegida no acredita autorización administrativa.
- No se repitió QA visual o E2E autenticado en navegador en esta entrega. Sigue vigente el checklist parcial23, incluidos ADMIN/trabajador, conflictos de formularios y teclado completo. Los nuevos caminos de carrito activo todavía necesitan pruebas de componentes/navegador al integrar la sesión comercial; Node no las sustituye.
- R2/CDN real sin validar: solo está configurada la URL pública, faltan cuenta, claves y bucket. Sin acceso de red de almacenamiento ni objetos modificados.

La primera ejecución de los nuevos tests detectó una referencia local incorrecta tras refactorizar el selector de cuenta (NameError); se corrigió y las ejecuciones posteriores pasan. No es un fallo histórico omitido.

## Pendientes exactos para terminar B4

| Trabajo | Estado / dependencia |
| --- | --- |
| Proveedor de contacto y entrega de pruebas |Operador debe definir canal/proveedor, credenciales de integración y cuotas. Registro público deshabilitado por decisión expresa |
| Registro, revisión/vínculo Customer y consentimiento |Falta implementación; definir aviso, retención y procedimiento de revisión. No reclamar Customer existente por coincidencia de email/documento |
| Sesión comercial y `/cuenta` |Falta implementación y pruebas de contexto explícito, usuario mixto, refresh y separación del acceso laboral; reutilizar login, sin crear membresías ERP |
| API de cálculo, resumen y confirmación en Next |Falta conectar servicios internos con contexto comercial verificado y errores recuperables; no utilizar ETag CMS como garantía de precio |
| Solicitud persistida/idempotencia y WhatsApp |Faltan modelo/contrato definitivo, API, historial, expiración/retención y UI de revisión. Destino solo del snapshot publicado; abrir enlace no es pedido recibido |
| Opt-in comercial |Falta campo defaultFalse auditado en WebsiteCatalogSettings y condiciones operativas. No crear un flag paralelo ni activar hasta aceptación |
| Datos del piloto |ADMIN elige lista/almacenes/productos; CMS publica identidad/contacto. No se prepararon registros habituales automáticamente |
| Medios reales y aceptación visual |R2/CDN autorizado y checklist23 pendientes |

Esta entrega no declara todos esos pendientes bloqueados únicamente por el proveedor: hay desarrollo de APIs, sesión e interfaz por realizar. Sí evita exponer un registro sin verificación y mantiene deshabilitados pedidos mientras se completa esa integración.

## Reproducción

Desde `apudig_mvp`, con PostgreSQL local disponible:

```powershell
.venv/Scripts/python.exe manage.py check
.venv/Scripts/python.exe manage.py makemigrations --check --dry-run
.venv/Scripts/python.exe docs/architecture/website-integration/audit_local_website.py --report b4d-local-environment-final.json
.venv/Scripts/python.exe docs/architecture/website-integration/run_catalog_security_checks.py --run-isolated . ../.tools/b4d-postgresql.json apps.websites apps.inventory.tests.test_catalog_api apps.inventory.tests.test_catalog_security apps.inventory.tests.test_product_images
```

El runner crea/migra/elimina exclusivamente la base desechable indicada. No ejecutar `migrate` en la base habitual como preparación de estas pruebas. Antes de incorporar cuentas al entorno habitual, revisar/autorizar0010 y preparar verificación/operación; el CMS y catálogo consultable actuales no requieren esa migración para sus lecturas.

Servicios locales (sin cambiar `.env`): backend `.venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000`; frontend `npm.cmd run dev -- --hostname 127.0.0.1`. Acceder a `http://demo.localhost:3000/` o `http://localhost:3000/` con el override de desarrollo existente. No activar flags ni crear datos comerciales para hacer desaparecer el estado vacío.
