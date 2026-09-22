# APUDIG MVP

ERP multiempresa para la gestión comercial, compras e inventario, construido como un monolito Django. La aplicación combina una interfaz web renderizada en servidor, una API REST versionada y servicios transaccionales para preservar el aislamiento por empresa y sucursal, el stock y la trazabilidad documental.

> Este documento describe únicamente funcionalidades verificadas en el código del repositorio. El nombre “MVP” se conserva porque forma parte del proyecto, aunque el alcance actual ya cubre varios flujos operativos completos.

## Estado actual

El proyecto se encuentra en desarrollo activo y dispone de módulos web funcionales para administración, socios comerciales, inventario, compras y ventas. También incluye una API v1 con autenticación JWT, catálogo e inventario, documentación OpenAPI y una suite de pruebas Django distribuida en 27 archivos.

No debe considerarse todavía una distribución de producción lista para exponer directamente a Internet: los contenedores incluidos ejecutan el servidor de desarrollo de Django y no incorporan proxy inverso, TLS, servidor WSGI/ASGI de producción, health checks, CI/CD ni una estrategia automatizada para archivos estáticos.

## Características principales

- Gestión multiempresa y multisucursal con selección de contexto activo.
- Usuario personalizado autenticado por correo electrónico.
- Roles y permisos granulares por empresa, además de acceso por sucursal.
- Catálogos de productos, categorías, marcas, unidades y socios comerciales.
- Múltiples unidades o presentaciones por producto con factores de conversión.
- Proveedores asociados a productos, código del proveedor y proveedor preferido.
- Listas de precios, precios por producto, lista predeterminada e importación masiva.
- Almacenes, ubicaciones, stock y movimientos trazables de inventario.
- Ciclos de compras y ventas con estados, impuestos, descuentos y auditoría.
- Reportes operativos y exportaciones Excel/CSV.
- Galería de hasta tres imágenes por producto almacenadas en Cloudflare R2.
- API REST v1 con JWT, paginación y esquema OpenAPI/Swagger.

## Módulos implementados

| Aplicación | Responsabilidad actual |
| --- | --- |
| `apps/core` | Modelos base, auditoría general, managers multiempresa, filtros compartidos y comando `seed`. |
| `apps/companies` | Empresas, branding, sucursales, accesos, configuración documental y preferencias operativas. |
| `apps/users` | Usuario personalizado, roles, permisos, asignaciones por empresa, accesos por sucursal, empleados y administración web. |
| `apps/partners` | Tipos de documento, clientes, perfiles/contactos comerciales, proveedores y transportistas. |
| `apps/inventory` | Maestros, productos, unidades, proveedores por producto, precios, almacenes, stock, movimientos, importaciones, imágenes y reportes. |
| `apps/purchases` | Categorías de gasto, órdenes, recepciones, documentos, conciliación, cuotas, pagos, costos adicionales y analítica. |
| `apps/sales` | Series, condiciones y medios de pago, cotizaciones, órdenes y documentos de venta. |
| `apps/api` | API v1, autenticación JWT, catálogo, inventario y administración de seguridad; reserva de namespace v2. |
| `apps/web` | Inicio, dashboard, cierre de sesión y navegación principal. |
| `apps/billing` | Aplicación histórica sin modelos operativos; se conserva para ejecutar sus migraciones de consolidación. |

## Arquitectura

APUDIG sigue una arquitectura de monolito modular:

- `models.py` define persistencia, restricciones e invariantes locales.
- `forms.py` valida entradas de la interfaz web.
- `selectors.py` concentra consultas reutilizables y filtradas por contexto.
- `services.py` y servicios especializados contienen flujos transaccionales.
- `views/` y `views.py` coordinan HTTP y mantienen la lógica crítica en servicios.
- `templates/` contiene la interfaz Django y `static/` los estilos y scripts del navegador.
- `apps/api/v1/` expone recursos mediante Django REST Framework.

Las entidades principales usan UUID. Los modelos con alcance empresarial emplean managers y filtros por `company_id` o `store_id`. Los movimientos de stock, emisión/anulación de ventas y procesos de compra relevantes se ejecutan dentro de transacciones de base de datos.

### Modelos principales

- Empresas: `Company`, `CompanyBranding`, `Store`, `UserCompanyAccess`, `CompanyDocumentSettings` y `CompanyOperationalSettings`.
- Seguridad: `User`, `Role`, `Permission`, `RolePermission`, `UserRole`, `UserStore`, `UserOperationalFlags` y `Employee`.
- Socios: `DocumentType`, `Customer`, `SalesCustomerProfile`, `SalesCustomerContact`, `Supplier` y `Carrier`.
- Inventario: `Product`, `Category`, `Brand`, `Unit`, `ProductUnit`, `ProductSupplier`, `PriceList`, `ProductPrice`, `Warehouse`, `WarehouseLocation`, `StockByWarehouse`, `Movement` y sus detalles/auditoría.
- Compras: `PurchaseOrder`, `PurchaseReceipt`, `PurchaseDocument`, sus líneas y conciliaciones, `PurchasePayableInstallment`, `SupplierPayment` y `PurchaseLandedCost`.
- Ventas: `DocumentSeries`, `PaymentMethod`, `MeansOfPayment`, `SalesQuotation`, `SaleOrder`, `SalesDocument` y sus líneas.
- Auditoría: `AuditLog` y `MovementAuditLog`.

## Stack tecnológico

| Componente | Tecnología declarada |
| --- | --- |
| Lenguaje | Python; la imagen Docker usa Python 3.11 |
| Framework web | Django `>=5.0,<6.0` |
| API | Django REST Framework `>=3.15` |
| OpenAPI | drf-spectacular `>=0.27` |
| Base de datos | SQLite o PostgreSQL mediante psycopg `>=3.2` |
| JWT | PyJWT `>=2.9` |
| CORS | django-cors-headers `>=4.3` |
| Excel | openpyxl `>=3.1` |
| Imágenes | Pillow `>=10.4` |
| Objetos externos | boto3 `>=1.35` para Cloudflare R2 |
| Contenedores | Docker y Docker Compose |

Las dependencias usan rangos mínimos y no existe un archivo de bloqueo; una instalación futura puede resolver versiones más recientes dentro de esos rangos.

## Estructura del proyecto

```text
apudig_mvp/
├── apps/
│   ├── api/v1/          # API REST vigente
│   ├── api/v2/          # Placeholder, aún sin recursos
│   ├── billing/         # Migraciones históricas
│   ├── companies/       # Empresas y sucursales
│   ├── core/            # Base, auditoría y seed
│   ├── inventory/       # Catálogo, stock y movimientos
│   ├── partners/        # Clientes, proveedores y transportistas
│   ├── purchases/       # Abastecimiento y cuentas por pagar
│   ├── sales/           # Cotizaciones, órdenes y ventas
│   ├── users/           # Usuarios, roles y permisos
│   └── web/             # Dashboard
├── bulk_up/             # Plantillas Excel incluidas
├── config/              # Settings, URLs, WSGI y ASGI
├── docs/                # Documentación detallada de ventas y compras
├── static/              # CSS, JavaScript e imágenes estáticas
├── templates/           # Plantillas por módulo
├── Dockerfile
├── docker-compose_apudig.yml
├── docker-compose_bd.yml
├── manage.py
└── requirements.txt
```

## Requisitos previos

- Python 3.11 o una versión compatible con Django 5 y las dependencias declaradas.
- `pip` y soporte para entornos virtuales.
- SQLite para el arranque local predeterminado, o PostgreSQL para un entorno compartido.
- Docker y Docker Compose si se utilizarán los contenedores incluidos.
- Una cuenta y bucket de Cloudflare R2 solo si se cargarán imágenes de productos.

## Instalación para desarrollo

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver
```

### Linux o macOS

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

La interfaz queda disponible en [http://127.0.0.1:8000/](http://127.0.0.1:8000/), la administración Django en `/admin/` y Swagger UI en `/api/docs/`.

## Variables de entorno

`config/settings.py` carga directamente el archivo `.env` de la raíz sin depender de `python-dotenv`. Las variables efectivamente consumidas son:

| Variable | Finalidad | Valor predeterminado del código |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Firma criptográfica de Django. | Inseguro y solo apto para desarrollo. |
| `DJANGO_DEBUG` | Activa debug cuando vale `1`. | `1` |
| `DJANGO_ALLOWED_HOSTS` | Hosts separados por comas. | `*` |
| `DJANGO_DB_ENGINE` | Backend de base de datos. | `django.db.backends.sqlite3` |
| `DJANGO_DB_NAME` | Archivo SQLite o nombre de base PostgreSQL. | `db.sqlite3` |
| `DJANGO_DB_USER` | Usuario de PostgreSQL. | Vacío |
| `DJANGO_DB_PASSWORD` | Contraseña de PostgreSQL. | Vacío |
| `DJANGO_DB_HOST` | Host de PostgreSQL. | Vacío |
| `DJANGO_DB_PORT` | Puerto de PostgreSQL. | Vacío |
| `CORS_ALLOWED_ORIGINS` | Orígenes CORS permitidos, separados por comas. | Frontends locales en puerto `3000` |
| `JWT_SECRET_KEY` | Clave para firmar JWT; debe ser independiente en producción. | Hereda `DJANGO_SECRET_KEY` |
| `JWT_ACCESS_TTL_HOURS` | Vigencia del token de acceso en horas. | `8` |
| `JWT_REFRESH_TTL_DAYS` | Vigencia del refresh token en días. | `30` |
| `R2_ACCOUNT_ID` | Account ID de Cloudflare de 32 caracteres. | Vacío |
| `R2_ACCESS_KEY_ID` | Identificador de credencial S3 para R2. | Vacío |
| `R2_SECRET_ACCESS_KEY` | Secreto de credencial S3 para R2. | Vacío |
| `R2_BUCKET_NAME` | Bucket que almacena imágenes. | Vacío |
| `R2_PUBLIC_BASE_URL` | URL pública base para construir las imágenes. | `https://media.apudig.com` |
| `PRODUCT_IMAGE_MAX_SIZE` | Tamaño máximo de carga en bytes. | `5242880` (5 MiB) |
| `PRODUCT_IMAGE_MAX_DIMENSION` | Máximo de ancho o alto tras redimensionar. | `1200` |
| `PRODUCT_IMAGE_WEBP_QUALITY` | Calidad WebP. | `82` |

El `.env.example` actual cubre Django, base de datos, R2 y límites de imagen, pero aún no lista `CORS_ALLOWED_ORIGINS`, `JWT_SECRET_KEY`, `JWT_ACCESS_TTL_HOURS` ni `JWT_REFRESH_TTL_DAYS`. Añádalas al `.env` cuando necesite valores distintos de los predeterminados. Nunca confirme `.env` ni secretos reales.

## Base de datos

SQLite es el backend predeterminado y resulta suficiente para desarrollo aislado. Para PostgreSQL, configure por ejemplo:

```dotenv
DJANGO_DB_ENGINE=django.db.backends.postgresql
DJANGO_DB_NAME=apudig_mvp
DJANGO_DB_USER=postgres
DJANGO_DB_PASSWORD=<valor-seguro>
DJANGO_DB_HOST=localhost
DJANGO_DB_PORT=5434
```

El puerto anterior corresponde al PostgreSQL publicado por los archivos Compose desde el puerto interno `5432`. Cuando Django se ejecuta dentro de `docker-compose_apudig.yml`, use `DJANGO_DB_HOST=db` y `DJANGO_DB_PORT=5432`.

Existen dos configuraciones locales:

- `docker-compose_apudig.yml`: aplicación Django más PostgreSQL 16; publica Django en `8000` y PostgreSQL en `5434`.
- `docker-compose_bd.yml`: PostgreSQL 15 más pgAdmin; publica PostgreSQL en `5434` y pgAdmin en `5050`.

No ejecute ambas composiciones simultáneamente sin cambiar nombres, puertos o volúmenes. Sus credenciales incluidas son exclusivamente valores locales de desarrollo y deben reemplazarse en cualquier entorno compartido.

## Migraciones

El repositorio contiene 67 migraciones de aplicación: 5 de `billing`, 10 de `companies`, 1 de `core`, 20 de `inventory`, 4 de `partners`, 11 de `purchases`, 13 de `sales` y 3 de `users`.

```bash
python manage.py migrate
python manage.py showmigrations
python manage.py makemigrations --check --dry-run
```

No elimine `apps/billing`: aunque no contiene modelos operativos, sus migraciones históricas consolidan datos hacia el modelo vigente de ventas.

## Datos iniciales y administrador

La forma estándar de crear un administrador vacío es:

```bash
python manage.py createsuperuser
```

También existe un seed idempotente para preparar unidades, tipos de documento, categorías base, marcas, listas de precios, roles, permisos de documentos de venta, una empresa/sucursal demo, series y un superusuario:

```bash
python manage.py seed --email admin@ejemplo.com --password "<contraseña-segura>" --company "Empresa Demo" --ruc "20000000001"
```

No use en un entorno real las credenciales predeterminadas del comando `seed`; proporcione siempre `--email` y `--password` explícitos.

## Ejecución

### Servidor local

```bash
python manage.py runserver
```

### Docker Compose

Prepare primero `.env` para que el servicio `web` se conecte a `db` y luego ejecute:

```bash
docker compose -f docker-compose_apudig.yml up --build
```

Para detenerlo:

```bash
docker compose -f docker-compose_apudig.yml down
```

El comando `down` no elimina el volumen persistente salvo que se solicite expresamente con opciones adicionales.

## Gestión multiempresa

La selección web en `/companies/select/` guarda `active_company_id` y `active_store_id` en la sesión. `ActiveCompanyMiddleware` valida el formato UUID y confirma que el usuario todavía tenga acceso al contexto antes de exponerlo a las vistas.

La seguridad se compone de:

- `UserCompanyAccess`: empresas y sucursales seleccionables por usuario.
- `UserRole`: roles asignados dentro de una empresa.
- `RolePermission`: permisos `read`, `manage` y `authorize` asociados a módulos.
- `UserStore`: rol operativo del usuario en una sucursal.
- superusuarios y rol empresarial `ADMIN`, que omiten controles subordinados dentro de su alcance.

Ventas aplica permisos `read.sales.documents`, `manage.sales.documents` y `authorize.sales.documents`. Compras evalúa el mismo esquema para `purchases.documents`. Si un módulo todavía no tiene permisos registrados, el evaluador conserva el acceso legado; cuando existe al menos un permiso del módulo, aplica denegación por defecto.

## Funcionalidades por módulo

### Empresas, usuarios y configuración

- Alta y mantenimiento de empresas, branding y sucursales.
- Datos comerciales, logos por URL, colores y formatos documentales.
- Preferencias de edición de cantidades/precios/totales, decimales e IGV predeterminado.
- Configuración de cliente, proveedor, tipo documental y condición de pago predeterminados.
- Política empresarial de stock negativo y bloqueo de movimientos por sucursal.
- Administración de usuarios, roles, permisos y asignaciones por empresa/sucursal.

### Socios comerciales

- Clientes por empresa con dirección, datos fiscales, perfil comercial y contactos.
- Proveedores y transportistas por empresa.
- Creación rápida de clientes y proveedores desde formularios operativos.
- Catálogo unificado de tipos de documento, con metadatos SUNAT y efectos declarativos.

### Inventario, productos y precios

- Productos inventariables o servicios, SKU único por empresa, código de barras, modelo, categoría y marca.
- Unidad principal y presentaciones alternativas con factor de conversión, precio de compra/venta y unidad predeterminada por operación.
- Relación producto-proveedor con código y nombre comercial del proveedor, preferencia y estado.
- Precio general de compra/venta y precios por listas en PEN u otra moneda registrada.
- Lista de precios predeterminada, activación/desactivación y carga masiva Excel.
- Búsqueda por nombre, SKU, código de barras, modelo y códigos/nombres del proveedor.
- Importación de categorías, marcas, unidades y productos desde `.xlsx` o `.csv`, con modo de validación y descarga de errores.
- Almacenes y ubicaciones por sucursal, stock agregado y stock por almacén.
- Entradas, salidas, transferencias y ajustes físicos en borrador; el stock cambia al confirmar.
- Correlativo anual de operación por sucursal, auditoría y bloqueo de edición posterior.
- Validación configurable de stock negativo y movimientos correctivos/reversiones trazables.
- Reportes de stock por almacén, comparativo, kardex y trazabilidad de movimientos, con salidas XLSX y vistas imprimibles.

### Compras

- Categorías de gasto y formulario separado para compras no asociadas a productos.
- Órdenes de compra con borrador, aprobación, cancelación y seguimiento de líneas; el modelo reserva además el estado `CLOSED`, pero no existe una acción web para cerrarlas.
- Recepciones parciales contra órdenes; generan entradas de inventario para productos inventariables.
- Documentos de proveedor con impuestos gravado/exonerado/inafecto, descuentos, moneda, tipo de cambio y almacén opcional.
- Documentos independientes de la orden, recepción y pago, con conciliación entre líneas facturadas y movimientos recibidos.
- Actualización del precio histórico de compra al registrar el documento.
- Cronogramas de cuotas, cuentas por pagar, pagos parciales/totales y anulación de pagos.
- Costos adicionales distribuidos por valor, cantidad base o asignación manual.
- Historial de precios en pantalla, vista imprimible y XLSX.
- Analítica de compras y exportación CSV del resumen por proveedor.

Para el flujo operativo detallado consulte [`docs/purchases_module.md`](docs/purchases_module.md).

### Ventas

- Series y correlativos por empresa, sucursal y tipo documental.
- Condiciones de pago (contado/crédito) y medios de pago.
- Cotizaciones con borrador, aprobación, rechazo, cancelación, copia y vistas imprimibles.
- Conversión de cotización aprobada a orden o documento, evitando conversiones duplicadas.
- Órdenes de venta con borrador, confirmación, facturación, cancelación y copia.
- Documentos de venta para notas de venta, facturas y boletas, consolidados en `SalesDocument` y `SalesDocumentLine`.
- Borradores, emisión con correlativo, copia, cancelación, anulación y nota de crédito.
- Impuestos por línea, descuentos por línea y globales, moneda y tipo de cambio.
- Salida de inventario al emitir y entrada de reversión al anular, cuando corresponde.
- Auditoría de creación, edición, emisión, cancelación y anulación.
- Detalles y plantillas HTML preparadas para imprimir desde el navegador como PDF; el backend no genera un archivo PDF binario.

Consulte también [`docs/sales_documents.md`](docs/sales_documents.md).

## Imágenes de productos y Cloudflare R2

Cada producto admite imagen principal, secundaria y terciaria. Antes de subirlas, Pillow:

1. valida que el archivo sea una imagen legible;
2. corrige orientación EXIF;
3. limita sus dimensiones;
4. aplana transparencias sobre fondo blanco;
5. convierte el resultado a WebP.

Los objetos se almacenan con las claves:

```text
products/{company_uuid}/{product_uuid}/main.webp
products/{company_uuid}/{product_uuid}/secondary.webp
products/{company_uuid}/{product_uuid}/tertiary.webp
```

La base de datos conserva las claves, no el binario. Las URLs públicas se construyen con `R2_PUBLIC_BASE_URL`. Las credenciales R2 son exclusivamente del backend; el bucket o dominio público debe configurarse por separado en Cloudflare.

## API e integraciones

### API REST v1

La API está montada bajo `/api/v1/` y admite autenticación de sesión o `Authorization: Bearer <token>`.

- Autenticación: obtención/renovación de tokens, perfil, empresas accesibles, selección de empresa y logout sin estado.
- Seguridad: listado/registro de usuarios y administración de roles/permisos para administradores autorizados.
- Inventario: categorías, marcas, unidades, almacenes, tipos documentales y productos.
- Catálogo: listado/detalle público y variantes privadas autenticadas; estas últimas incluyen precio de compra.
- Documentación: esquema en `/api/schema/` y Swagger UI en `/api/docs/`.

Los módulos `/api/v1/sales/` y `/api/v1/companies/` no exponen endpoints todavía. `/api/v2/` responde como placeholder no implementado. La API no usa un framework externo de revocación: el logout JWT actual es un `204` sin lista negra y los tokens permanecen válidos hasta expirar.

### Servicios externos

La única integración externa operativa encontrada es Cloudflare R2 mediante su API compatible con S3. No hay proveedores de correo, pagos, bancos, contabilidad ni servicios SUNAT conectados en el código actual.

## Facturación electrónica

`SalesDocument` contiene estados y campos reservados para XML, CDR y respuestas SUNAT, y `DocumentType` identifica documentos SUNAT. Sin embargo, todavía no existe generación/firma de XML, envío a SUNAT u OSE, consulta de estado, procesamiento de CDR ni almacenamiento electrónico implementado. Las facturas, boletas y notas de crédito actuales son documentos comerciales internos y no deben presentarse como emisión electrónica homologada.

## Pruebas y validación

Los tests usan `django.test.TestCase`. `config/settings_test.py` cambia la base de datos a SQLite en memoria para una ejecución aislada.

```bash
python manage.py test --settings=config.settings_test
python manage.py test apps.inventory --settings=config.settings_test
python manage.py test apps.purchases --settings=config.settings_test
python manage.py test apps.sales --settings=config.settings_test
python manage.py check
python manage.py makemigrations --check --dry-run
```

Si el entorno virtual fue movido, se eliminó su intérprete base o cambió la versión de Python, recréelo antes de ejecutar estos comandos; los entornos virtuales no son portables.

## Despliegue y producción

Los archivos Docker actuales son apropiados para desarrollo. Para desplegar en producción se requiere, como mínimo:

1. fijar versiones reproducibles de dependencias;
2. establecer `DJANGO_DEBUG=0`, una clave secreta aleatoria y hosts explícitos;
3. configurar PostgreSQL con credenciales y copias de seguridad gestionadas;
4. ejecutar migraciones como paso controlado del despliegue;
5. ejecutar `python manage.py collectstatic --noinput` y servir `STATIC_ROOT`;
6. sustituir `runserver` por un servidor WSGI/ASGI de producción;
7. colocar un proxy con HTTPS, límites de carga y cabeceras de seguridad;
8. configurar orígenes CORS exactos y secretos JWT/R2 independientes;
9. añadir observabilidad, rotación de logs, health checks y política de recuperación;
10. verificar aislamiento multiempresa y acceso al catálogo antes de publicar la API.

El repositorio no incluye todavía una receta que implemente esos pasos; deben adaptarse a la plataforma elegida.

## Comandos útiles

```bash
# Comprobaciones
python manage.py check
python manage.py showmigrations
python manage.py makemigrations --check --dry-run

# Base de datos
python manage.py migrate

# Usuarios y datos iniciales
python manage.py createsuperuser
python manage.py seed --email admin@ejemplo.com --password "<contraseña-segura>"

# Desarrollo
python manage.py runserver

# Pruebas
python manage.py test --settings=config.settings_test

# Estáticos para un despliegue preparado
python manage.py collectstatic --noinput
```

## Consideraciones de seguridad

- Nunca confirme `.env`, tokens, claves R2, contraseñas ni datos productivos.
- Reemplace todos los secretos y credenciales demo antes de compartir un entorno.
- No use `DJANGO_ALLOWED_HOSTS=*`, `DJANGO_DEBUG=1` ni la clave predeterminada en producción.
- Use una `JWT_SECRET_KEY` fuerte e independiente y considere revocación/rotación de refresh tokens.
- Valide siempre empresa, sucursal, almacén y propietario en consultas o endpoints nuevos.
- Mantenga las credenciales R2 solo en el backend y limite su política al bucket/ruta necesarios.
- Revise el catálogo público antes de exponerlo: sus vistas usan `AllowAny` y, sin contexto de empresa, el filtrado compartido no restringe por compañía.
- La configuración CORS solo debe contener orígenes confiables; `CORS_ALLOW_CREDENTIALS` está desactivado.
- Proteja PostgreSQL y pgAdmin de exposición pública; los puertos publicados por Compose son para desarrollo local.
- Los campos preparados para SUNAT no equivalen a cumplimiento tributario ni facturación electrónica válida.

## Limitaciones y evolución identificable

Solo se listan elementos respaldados por placeholders, campos sin integración o documentación técnica existente:

- Implementar recursos reales en API v2 y en los namespaces API v1 de ventas y empresas.
- Corregir la descarga XLSX de cotizaciones: la ruta existe, pero la vista actual usa una variable no definida al construir el nombre del archivo.
- Incorporar facturación electrónica/SUNAT completa si forma parte del alcance futuro.
- Añadir revocación o rotación de refresh tokens JWT.
- Crear una configuración reproducible y endurecida de producción.
- Integrar costos adicionales en la valorización de kardex; actualmente se conservan como distribución histórica.
- Completar devoluciones a proveedor, matching de tres vías con tolerancias/aprobación, conciliación bancaria y contabilidad, todavía no implementados.
- Ampliar permisos específicos de compras más allá de las acciones generales `read/manage/authorize`.
- Sincronizar `.env.example` con las variables CORS y JWT utilizadas por settings.

## Notas para desarrolladores

- Mantenga reglas de negocio en servicios y consultas reutilizables en selectores.
- Toda operación que modifique stock debe ser atómica y usar los servicios de inventario.
- No cree modelos paralelos para facturas o boletas: el modelo canónico es `SalesDocument`.
- Preserve las migraciones de `billing` aunque la aplicación sea legado.
- Añada migraciones junto con cualquier cambio de esquema y pruebas enfocadas para reglas, permisos y aislamiento.
- Las entidades empresariales nuevas deben filtrar explícitamente por empresa/sucursal y validar relaciones cruzadas.
- Las vistas llamadas `*_pdf` entregan HTML imprimible salvo que el código indique expresamente otro formato.
- Antes de integrar cambios ejecute pruebas del módulo, la suite global, `check` y la comprobación de migraciones.
