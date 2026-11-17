# Remediación P0 de catálogos laborales

Actualización posterior del mismo día: el usuario autorizó el catálogo básico a todos los miembros de la empresa, sin rol ni permiso ERP de productos. Se mantienen contexto/membresía y exclusividad administrativa de datos privados. La navegación también oculta vistas administrativas a usuarios comunes. La política vigente, pruebas y requisito futuro para clientes verificados están en [18](18-acceso-catalogo-miembros.md); las referencias a permiso de lectura de catálogo que siguen describen la implementación inicial.

Fecha: 17/11/2026. Continúa los informes [15](15-cierre-b3-a-y-remediacion-p0.md) y [16](16-contratos-y-politica-b4-b.md). Implementación de seguridad previa a B4-B; no implementa K0–K7 ni activa comercio.

## Decisiones confirmadas y alcance

El usuario aprobó que `/catalog` requiera el login APUDIG existente y una empresa seleccionada. Los costos de compra, listas internas, almacenes y códigos de proveedor quedan reservados a superusuario o administrador **de empresa**, con contexto válido. Ser administrador de una sucursal no concede esos datos privados.

Ramas conservadas: backend `websites_backend`, base `9e9eaf5`; frontend `mvp_website`, base `83eb3ac`. La rama backend real difiere del `develop` de la planificación inicial; no se hizo checkout. Se preservaron documentos no confirmados de entregas anteriores. No se modificaron `.env`, credenciales, modelos, migraciones, precios, stock ni registros de la base habitual. Sin commits, push o despliegues.

## Contratos y consumidores

Se conserva `/api/v1/` y las seis rutas GET existentes:

| Ruta | Consumidor observado | Acceso después del ajuste |
| --- | --- | --- |
| `catalog/products/` | `getCatalogProducts` → `/catalog`, CatalogPage/ProductCard | JWT + empresa + lectura vigente; proyección básica |
| `catalog/products/{uuid}/detail/` | `getProductDetail` → ProductDetailModal | Igual; sin datos privados, incluso para administradores en esta ruta |
| `catalog/private/products/` | `getCatalogProductsPrivate` → `/admin/catalog_admin` | Superusuario o administrador de empresa |
| `catalog/private/products/{uuid}/detail/` | `getPrivateProductDetail` → modal administrativo | Igual; relaciones privadas acotadas al contexto |
| `products/` | `getProducts`, listados/selectores de productos administrativos conservados en Next | Lectura vigente; campos privados solo para administración de empresa |
| `products/{uuid}/` | Contrato genérico de lectura de inventario; sin consumidor activo adicional del detalle observado en Next | Igual; no permite eludir la protección del catálogo |

El inventario de consumidores se realizó antes del parche y consta en el informe15. Los formularios ERP históricos de Next muestran una transición a Django. No se implementaron operaciones POST/PUT/DELETE nuevas. Otros clientes externos no pueden descartarse solo con el rastreo del repositorio: el operador debe inventariarlos antes de un corte productivo y actualizar su autenticación/contexto. No se mantiene una ventana anónima insegura.

Se mantienen URLs, búsqueda básica, filtros UUID de marca/categoría, imágenes, campos de venta y paginación laboral `total/limit/offset/results`. La búsqueda por código/nombre de proveedor se conserva exclusivamente en el endpoint privado. Los filtros UUID malformados devuelven400; no se ignoran para ampliar una consulta.

La retirada de campos privados y de lectura anónima es el cambio de contrato de seguridad aprobado. `/catalog` no es el futuro catálogo público Website. El layout histórico y sus nombres propios se conservan; su identidad visual fija sigue siendo deuda independiente, no una fuente de autorización.

## Autorización y aislamiento

`catalog/access.py` reutiliza la validación JWT existente y añade challenge Bearer y manejo de credenciales malformadas, sin cambiar login/refresh ni el autenticador global.

Antes de seleccionar productos comprueba usuario activo, UUID Company firmado obligatorio, Company activa, Store activa de esa empresa si existe, membresía actual `UserCompanyAccess` y acceso vigente al contexto. Para usuarios no administradores exige el permiso actual `read.inventory.products` mediante roles ERP. No utiliza el fallback histórico que concede acceso cuando falta la configuración de un módulo. Un administrador de sucursal puede leer lo básico en su contexto vigente; los campos privados requieren administración de empresa.

Los superusuarios también deben seleccionar Company; una query `company_id` no reemplaza la claim firmada. Se revalidan roles/membresías en cada solicitud: los claims antiguos no conceden acceso. Sin contexto válido se deniega antes de ejecutar el selector de productos.

| Situación | Resultado |
| --- | --- |
| Sin JWT / JWT inválido o expirado | 401, `WWW-Authenticate: Bearer` |
| Sin Company o UUID/contexto inválido | 403 |
| Company/Store inactiva, membresía revocada o sin permiso | 403 |
| Lector básico en endpoint privado | 403 |
| UUID de producto ajeno o inactivo | 404 |

Se conserva el formato de errores DRF `detail` o campos de validación. El transporte Next existente conserva `status`, `code`, `fields`, ETag y Retry-After cuando el backend los proporciona; el catálogo heredado no incorpora el envelope de errores Website. `COMPANY_REQUIRED` es el código interno DRF de contexto, no una nueva promesa de campo JSON.

`catalog/selectors.py` envuelve `get_products` con contexto obligatorio. No se alteraron el helper global ni las reglas operativas ERP. Producto, categorías/marcas, listas activas y proveedores se acotan a la Company. El stock considera almacenes y sucursales activos de la empresa y, si hay sucursal seleccionada, solo esa sucursal. Relaciones históricas corruptas de otros tenants se excluyen defensivamente; sus nombres y códigos tampoco son buscables. En este catálogo privado, contexto de empresa sin sucursal representa acceso empresarial; no es la futura política pública de almacenes explícitos de B4.

Serializers básicos separados evitan anunciar costos/proveedores/listas/almacenes en el contrato básico. Los serializers privados conservan nombres de campos autorizados. Las respuestas llevan `Cache-Control: private, no-store` y `Vary: Authorization` conservando otros valores Vary.

## Cliente Next.js

`/catalog` usa AuthGuard y el login/selección de empresa existentes. CatalogWorkspace se remonta al cambiar usuario, Company, Store o modo básico/privado: limpia selección, paginación, filtros y productos. Las solicitudes admiten AbortSignal y descartan respuestas de componentes desmontados. Los errores401/403 liberan la carga y eliminan los resultados anteriores.

Se eliminó la caché global por ID del modal. El detalle se solicita de nuevo, cancela solicitudes anteriores y muestra errores. Tarjetas/modal no inventan un costo0 cuando el servidor omite el campo. El flag `isAdmin` elige la ruta/presentación, pero nunca autoriza datos: esa decisión corresponde a Django.

No se cambió la autenticación general, el diseño del storefront, Website ni `/shop`. Comercio permanece deshabilitado.

## Archivos funcionales

Backend nuevos: `apps/api/v1/catalog/access.py`, `selectors.py`, `schema.py`; `apps/inventory/tests/test_catalog_security.py`.

Backend modificados: `apps/api/v1/catalog/views.py`, `serializers.py`; `apps/api/v1/inventory/views.py`, `serializers.py`; `apps/inventory/apps.py` (registro del esquema Bearer de catálogo); `apps/inventory/tests/test_catalog_api.py`.

Frontend modificados: `src/components/catalog/CatalogPage.jsx`, `src/components/admin/ProductCard.jsx`, `ProductDetailModal.jsx`, `src/services/productsService.js`, `tests/storefront-smoke.mjs`, además de los documentos de continuidad y matriz/rutas.

Pruebas históricas corregidas: usaban alias `/catalog/...` fuera del prefijo real y subjects JWT sin usuario existente. Ahora crean usuario/membresía/rol reales y comprueban las rutas `/api/v1/`. Los casos de costo se ejecutan como administrador en el endpoint privado; la proyección básica exige ausencia de campos privados. No se cambiaron expectativas de las pruebas ERP no relacionadas.

## Validación y evidencia

- PostgreSQL local, base desechable `test_apudig_catalog_p0_tests`; fixtures sintéticos A/B y migraciones automáticas exclusivamente dentro de esa base. La base habitual `apudig_mvp` no recibió migraciones ni escrituras de esta entrega.
- 156 pruebas acotadas correctas: 13 de seguridad + 10 de contrato de catálogo + 113 Website + 20 administración de usuarios.
- Frontend: lint y build correctos, 45 pruebas Node correctas, smoke HTTP de16 rutas correcto.
- Ocho comprobaciones HTTP adicionales: las seis lecturas ERP sin token devuelven401; Next con Host `demo.localhost` devuelve200 y con Host desconocido404. [Evidencia sin datos de respuesta](p0-http.json).
- `manage.py check`: sin problemas. `makemigrations --check --dry-run`: sin cambios.
- OpenAPI generado con esquema Bearer propio para catálogo y proyecciones básicas separadas. La exportación global mantiene errores/advertencias en APIs históricas; no constituye una validación global del esquema ERP.

La comparación diferencial y los identificadores completos se entregan en [p0-regresion.json](p0-regresion.json): baseline680 casos,83 fallos y35 errores; versión final693 casos,78 fallos y35 errores, **sin casos nuevos fallidos**. PostgreSQL18.1. La suite ERP global sigue fallando; no se declara aprobada. Los cinco casos históricos de catálogo que mejoraron con las correcciones de fixtures/contrato se distinguen de los fallos ERP conservados.

### Reproducción segura

Desde backend, ejecutar de forma secuencial; el usuario PostgreSQL local necesita permiso de crear bases de prueba. El runner toma solo credenciales locales de la configuración existente, no las imprime y fuerza una base de prueba con nombre independiente:

```powershell
.\.venv\Scripts\python.exe docs\architecture\website-integration\run_catalog_security_checks.py --run-isolated . ..\.tools\catalog-focused.json apps.inventory.tests.test_catalog_security apps.inventory.tests.test_catalog_api apps.websites apps.users.tests.test_company_administration
.\.venv\Scripts\python.exe docs\architecture\website-integration\run_catalog_security_checks.py --run-isolated . ..\.tools\catalog-all.json
```

El runner devuelve código distinto de cero si fallan pruebas. Para comparación, preparar una copia explícita del baseline e indicar su ruta como REPOSITORY, sin ejecutar checkout/merge. `catalog_security_probe.py` y `catalog-security-probe.json` se conservan como diagnóstico histórico anterior al parche; sus expectativas inseguras no son tests de aceptación actuales y no deben sobrescribirse para simular una corrección.

Frontend, con dependencias existentes:

```powershell
npm.cmd run lint
npm.cmd run build
node --test tests/*.test.mjs
npm.cmd run start -- --port 3110
# En otra consola, con Django en localhost:8000 y el dominio activo existente:
node tests/storefront-smoke.mjs http://127.0.0.1:3110 demo.localhost
```

Para uso local normal, iniciar Django con `.\.venv\Scripts\python.exe manage.py runserver` y Next con `npm.cmd run dev`. Abrir `/login`, seleccionar empresa y luego `/catalog` o `/admin/catalog_admin`. En `next start`, el override `WEBSITE_DEV_HOSTNAME` no está activo: abrir el dominio registrado para el Website público. El catálogo laboral protegido no necesita resolver un dominio público.

## Limitaciones y siguiente revisión

El navegador integrado informó host no disponible; la alternativa nativa se detuvo al no poder determinar con seguridad la URL actual de Chrome. No se validaron visualmente login/refresh, cambio de empresa, scroll/filtros/modal ni responsive con una sesión real. HTTP/compilación y tests de API no demuestran esa interacción. Debe realizarla el operador antes de desplegar. No se generaron ni utilizaron credenciales de usuarios reales para suplir esa limitación.

B3-A sigue parcialmente aceptado por QA visual y R2/CDN real pendientes. Se conserva la autorización anterior de usar R2 simulado; no hubo pruebas de escritura reales. `demo.localhost` se había observado activo/verificado por el operador; esta entrega no atestiguó ni modificó dominios.

Otras APIs ERP con contexto opcional requieren auditoría independiente; esta remediación no certifica la seguridad de todo el ERP. Faltan inventario de consumidores externos y coordinación del corte. Los fallos ERP globales y avisos de esquema permanecen visibles en la evidencia.

Antes de B4-B revisar la política del informe16: lista pública y roles autorizados, precios/unidades/impuestos, almacenes explícitos y opt-in comercial. No se implementaron catálogo público K0–K3, administración K4–K7, cotizaciones, carrito comercial ni B4-C/D.
