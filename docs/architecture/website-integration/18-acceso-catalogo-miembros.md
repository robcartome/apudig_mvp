# Catálogo laboral para todos los miembros de la empresa

Fecha: 17/11/2026. Ajuste solicitado después de la entrega17. Esta decisión sustituye la exigencia de `read.inventory.products` **solo para el catálogo laboral básico**; conserva las demás validaciones P0.

## Política vigente

| Usuario | `/catalog` | Catálogo privado / administración de empresa |
| --- | --- | --- |
| Activo, miembro vigente de la empresa, sin rol | Permitido | Denegado |
| SELLER / CASHIER u otro rol no administrativo | Permitido | Denegado |
| ADMIN de la empresa seleccionada | Permitido | Permitido |
| Superusuario con empresa seleccionada | Permitido | Permitido |
| Anónimo, sin empresa, empresa inactiva o membresía revocada | Denegado | Denegado |

Estar registrado en APUDIG sin pertenecer a la empresa no concede acceso a su catálogo. Se mantienen JWT, Company activa, pertenencia actual, aislamiento de productos y validación vigente de sucursal cuando el token la incluye. No se permite elegir otra empresa mediante query o formulario. No se asignan roles o permisos a usuarios ni se cambian registros reales.

`CatalogAccessMixin.require_product_permission` conserva `True` por defecto. Las vistas del catálogo laboral usan `False`; las lecturas genéricas `/api/v1/products/` mantienen el permiso ERP actual. Los endpoints privados siguen comprobando `can_view_private`: superusuario o ADMIN de Company. Los serializers básicos nunca devuelven compra, proveedores, listas internas o detalles por almacén.

## Navegación y vistas

Next usa el perfil obtenido de `/auth/me/`, con roles de la Company coincidentes con la empresa seleccionada, para decidir qué accesos presentar. La respuesta añade `is_superuser` calculado desde el usuario real, sin modificar la emisión/validación JWT ni confiar en un claim enviado por el cliente. La autorización efectiva permanece en Django.

El sidebar oculta inicio administrativo y catálogo privado a usuarios comunes. Si abren directamente `/admin`, `/admin/catalog_admin` o una ruta ERP, AdminLayout presenta únicamente un enlace al catálogo laboral y no monta la vista administrativa ni su navegación. El catálogo `/catalog` conserva su layout sin enlaces administrativos.

Los permisos CMS explícitos existentes siguen permitiendo entrar al editor Website, sin conceder administración empresarial ni datos del catálogo privado. No se elimina ese flujo editorial autorizado por no tener rol ADMIN. El control servidor del CMS permanece intacto.

Archivos de este ajuste: backend `catalog/access.py`, `catalog/views.py`, `users/views.py`, `inventory/tests/test_catalog_security.py`; frontend `lib/admin/access.mjs`, `components/layout/AdminLayout.jsx`, `Sidebar.jsx`, `app/(admin)/admin/page.js`, `tests/admin-access.test.mjs` y documentación de continuidad.

## Clientes verificados: requisito futuro, sin implementación

El registro desde el Website no otorgará automáticamente membresía laboral `UserCompanyAccess`, rol ERP ni acceso a listas internas. La futura admisión comercial debe vincular el cliente a la empresa del Website, verificarlo, aprobarlo explícitamente y permitir revocación por la empresa.

Los precios mayoristas/distribución se resolverán según la lista autorizada para ese cliente y empresa; nunca por un `company_id`, nombre de rol, lista o precio recibido del navegador. El login no equivale a aprobación comercial. No reutilizar este permiso de catálogo laboral como atajo de acceso para clientes.

El diseño futuro debe contemplar estado de verificación/aprobación, responsable y evidencia, listas permitidas por segmento/cliente y empresa, revocación, aislamiento, caché por contexto comercial y separación de precios públicos de precios privados del cliente. Conciliar primero los modelos reales de Customer/usuario/precios y los contratos B4: no se crean modelos, migraciones, endpoints de registro comercial ni comercio en esta entrega.

## Validación

- PostgreSQL18.1, base de prueba desechable `test_apudig_catalog_p0_tests`, sin escrituras en `apudig_mvp` habitual.
- Pruebas de miembros sin rol, SELLER y CASHIER: listado/detalle básicos200; datos privados ausentes; privado403; detalle ajeno404; membresía revocada403.
- La retirada de permisos ERP no bloquea el catálogo básico y sí conserva403 en `/products/`; claims ADMIN antiguos no conceden acceso privado.
- El perfil devuelve el estado real de superusuario aunque el JWT contenga una afirmación contraria. Tests de UI cubren miembros/roles, superusuario, ADMIN de Company, cambio de empresa y permisos CMS separados.
- Frontend: lint y build correctos;49 pruebas Node correctas. `manage.py check` sin problemas.
- Primera ejecución acotada:157 pruebas correctas de catálogo/Website/administración. Se añadió después el test del perfil de superusuario, que pasó en la ejecución global final.
- Regresión final:695 pruebas;78 fallos y35 errores heredados, exactamente los mismos casos fallidos de la entrega17, sin casos nuevos fallidos. No equivale a una suite ERP global aprobada.

La regresión final y sus resultados se guardan en [catalog-members-regresion.json](catalog-members-regresion.json). Las pruebas de presentación de este ajuste son de lógica y compilación; la interacción visual autenticada sigue pendiente por la limitación de navegador ya registrada en17. No se repitió ni se afirma una validación R2 real. Sin commits, push, despliegues o cambios de rama/configuración.
