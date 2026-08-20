# APUDIG MVP

Sistema ERP multiempresa construido como monolito Django. El repositorio organiza los dominios en `apps/`, con módulos para ventas, inventario, socios comerciales, empresas, usuarios y APIs versionadas.

## Requisitos

- Python 3.13
- PostgreSQL 16 para desarrollo integrado o SQLite para ejecución básica
- Dependencias declaradas en `requirements.txt`

## Instalación local

```bash
python -m venv .venv
pip install -r requirements.txt
```

Active el entorno virtual y copie `.env.example` como `.env`. Después ejecute:

```bash
python manage.py migrate
python manage.py seed
python manage.py runserver
```

En PowerShell, active el entorno con `.\.venv\Scripts\Activate.ps1`. La aplicación estará disponible en [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

## Docker y PostgreSQL

Configure PostgreSQL en `.env` y levante los servicios con:

```bash
docker compose -f docker-compose_apudig.yml up --build
```

El contenedor publica Django en el puerto `8000` y PostgreSQL en el puerto local `5434`.

## Estructura principal

- `config/`: configuración y URLs generales de Django.
- `apps/sales/`: cotizaciones, pedidos y documentos de venta.
- `apps/inventory/`: productos, almacenes, movimientos, stock y trazabilidad.
- `apps/partners/`: clientes, proveedores y transportistas.
- `apps/companies/`: empresas, sucursales y acceso multiempresa.
- `apps/users/`: usuarios, roles y permisos.
- `apps/api/v1/`: API REST versionada.
- `templates/` y `static/`: interfaz web y JavaScript.

## Documentos de venta

Notas de venta (`NV`), facturas (`01`) y boletas (`03`) se almacenan exclusivamente en `SalesDocument` y `SalesDocumentLine`. No se deben crear modelos paralelos como `Voucher`, `Sale` o `BillingInvoice`. La aplicación `billing` permanece únicamente para ejecutar migraciones históricas.

El flujo implementado incluye:

- Creación y edición de borradores en `/sales/documents/`.
- Numeración correlativa segura al emitir.
- Conversión idempotente de cotizaciones aprobadas.
- Salidas de inventario para productos inventariables.
- Validación configurable de stock negativo por almacén.
- Reversión trazable de inventario al anular.
- Auditoría de creación, edición, emisión, cancelación y anulación.
- Aislamiento por empresa y sucursal.

Los permisos disponibles son `read.sales.documents`, `manage.sales.documents` y `authorize.sales.documents`. Consulte [docs/sales_documents.md](docs/sales_documents.md) para las reglas completas.

## Pruebas y validación

```bash
python manage.py test apps.sales
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
```

Las pruebas de ventas incluyen concurrencia de correlativos, cálculo tributario, permisos, auditoría, conversión desde cotización e integración con inventario. La suite global conserva cuatro pruebas antiguas de catálogo que esperan rutas sin versionar (`/catalog/products`); el API vigente utiliza `/api/v1/catalog/products/`.

## Seguridad

No confirme `.env`, credenciales ni datos productivos. Registre nuevas variables en `.env.example` usando valores seguros y valide siempre el alcance de empresa, sucursal y almacén en consultas nuevas.
