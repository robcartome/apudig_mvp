# Documentos de venta

El módulo de ventas usa exclusivamente `SalesDocument` y `SalesDocumentLine` para notas de venta (`NV`), facturas (`01`) y boletas (`03`). Las tablas son `sales_documents` y `sales_document_lines`. La aplicación `billing` se conserva únicamente para ejecutar migraciones históricas; no contiene modelos operativos.

## Flujo

1. Crear el borrador en `/sales/documents/new/`.
2. Editar cabecera y líneas mientras el estado sea `DRAFT`.
3. Emitir para reservar el correlativo y cambiar a `ISSUED`.
4. Si se habilitó inventario, la emisión crea una salida confirmada con origen `SALE`.
5. Anular crea una entrada `SALE_REVERSAL`; nunca elimina el movimiento original.

Una cotización aprobada puede convertirse una sola vez desde su detalle. La venta conserva `source_quotation` y la cotización no cambia de estado.

## Permisos

- `read.sales.documents`: listar, consultar y generar PDF.
- `manage.sales.documents`: crear, editar y cancelar borradores.
- `authorize.sales.documents`: emitir, anular y crear notas de crédito.

Los permisos se evalúan por empresa mediante `UserRole`. Ejecutar `python manage.py seed` crea las asignaciones iniciales.

## Inventario y auditoría

Solo las líneas cuyo producto tenga `tracks_inventory=True` afectan stock. El almacén debe pertenecer a la sucursal activa. El stock negativo depende de `Warehouse.allow_negative_stock`. Todas las transiciones relevantes generan registros en `AuditLog` y los movimientos mantienen la relación navegable con el documento.

## Verificación

```bash
python manage.py migrate
python manage.py test apps.sales
python manage.py makemigrations --check --dry-run
```
