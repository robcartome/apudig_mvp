# Módulo de Compras

## Propósito y alcance

El módulo registra el ciclo de abastecimiento y deuda con proveedores, conservando la trazabilidad entre la orden, la recepción física, el comprobante del proveedor, las cuotas, los pagos y los costos adicionales.

La regla central es que estos hechos son independientes:

- una **recepción** incrementa inventario;
- un **documento de compra** registra la factura, boleta u otro comprobante del proveedor;
- un **pago** reduce la deuda;
- un **costo adicional** distribuye importes complementarios sobre las líneas de una compra.

Esto permite, por ejemplo, recibir mercadería antes de recibir la factura, registrar servicios que no afectan stock y pagar una factura en varias cuotas.

## Resumen de lo implementado

| Fase | Entregable | Resultado |
| --- | --- | --- |
| 1 a 4 | Documentos de compra y líneas | Borradores, registro, anulación, impuestos, proveedor, sucursal, almacén y actualización del precio histórico de compra. |
| 5 | Historial de precios | Consulta de precios de compra por producto y proveedor. |
| 6 | Compras de servicios y gastos | Comprobantes con productos del catálogo y formulario separado para gastos por categoría. |
| 7 | Órdenes de compra | Creación, edición, aprobación, cancelación y seguimiento de líneas. |
| 8 | Recepciones | Recepciones parciales por orden y generación del movimiento de entrada a inventario. |
| 9 | Cuentas por pagar y pagos | Cuotas, pagos a proveedor, aplicaciones y estados no pagado, parcial o pagado. |
| 10 | Costos adicionales | Distribución por valor, cantidad o asignación manual. |
| 11 | Reportes | Analítica, cuentas por pagar, historial de precios y exportación CSV de proveedores. |

## Tipos de documento y trazabilidad

Para identificar qué se realizó, cada operación tiene un **tipo documental funcional**, su número y estado. El comprobante fiscal del proveedor se registra además mediante el tipo, serie y número del documento de compra.

| Tipo documental funcional | Qué representa | Número | Estado principal | Impacto |
| --- | --- | --- | --- | --- |
| Orden de compra | Solicitud o compromiso de compra al proveedor | `order_number` | Borrador, Aprobada, Cerrada, Cancelada | No modifica stock ni deuda. |
| Recepción de compra | Ingreso físico parcial o total de una orden | `receipt_number` | Registrada, Cancelada | Crea o revierte una entrada de inventario. |
| Documento de compra | Factura, boleta u otro comprobante del proveedor | Tipo + serie + número | Borrador, Registrado, Cancelado | Registra la compra y genera la cuenta por pagar; puede crear entrada de inventario si corresponde. |
| Cuota por pagar | Vencimiento de una deuda originada por un documento | Secuencia de cuota | Pendiente, parcial o pagada según sus aplicaciones | No modifica inventario. |
| Pago a proveedor | Pago registrado contra una o varias cuotas | `payment_number` | Registrado, Anulado | Reduce deuda mediante aplicaciones. |
| Costo adicional | Flete, seguro, aduana u otro costo asociado | Registro de costo adicional | Distribuido, Anulado | Distribuye un importe histórico sobre líneas de compra. |

### Cómo interpretar los vínculos

```text
Orden de compra
 ├─ Recepción 1 ──> Movimiento de inventario (entrada)
 ├─ Recepción 2 ──> Movimiento de inventario (entrada)
 └─ Documento de compra ──> Cuotas ──> Pago(s)
                              │
                              └─ Costo(s) adicional(es) distribuido(s)
```

No todos los vínculos son obligatorios. Una factura puede no tener orden previa; una orden puede recibirse en varias entregas; y una compra de servicio puede no tener almacén ni movimiento de stock.

## Manual operativo

### 1. Preparación

Antes de registrar una compra, verificar que estén creados y asignados a la empresa y sucursal correctas:

- proveedor y su tipo de documento;
- sucursal y almacén;
- productos, unidades y configuración de control de inventario;
- categorías de gasto para alquileres, honorarios y otros conceptos no asociados a un producto;
- medios de pago para registrar pagos posteriores.

El almacén seleccionado debe pertenecer a la sucursal del documento. Si aparece el mensaje *“El almacén debe pertenecer a la sucursal del documento”*, se debe elegir un almacén de la sucursal activa o corregir la configuración del almacén.

### 2. Registrar una orden de compra

1. Ir a **Compras > Órdenes** y crear una nueva orden.
2. Seleccionar proveedor, sucursal, moneda, fecha y líneas.
3. Para cada línea elegir un producto del catálogo. Los servicios también se crean como productos, con control de inventario desactivado.
4. Guardar como borrador mientras se ajustan cantidades o precios.
5. Aprobarla cuando sea el compromiso válido con el proveedor.

Una orden aprobada sirve como base para recepciones y para contrastar posteriormente cantidades y precios facturados.

### 3. Registrar la recepción de mercadería

1. Desde el detalle de la orden aprobada seleccionar **Nueva recepción**.
2. Confirmar almacén, fecha y cantidades realmente recibidas.
3. Registrar la recepción.

La recepción puede ser parcial. Al registrarla, el sistema genera la entrada de inventario únicamente para productos que controlan stock. Si se anula, se genera la reversión correspondiente; no se elimina el historial del movimiento original.

### 4. Registrar el documento de compra

1. Ir a **Compras > Documentos > Nuevo documento**.
2. Seleccionar proveedor, tipo de comprobante, serie, número, operación, sucursal y, cuando aplique, almacén.
3. Vincular la orden de compra si la factura proviene de una.
4. Agregar líneas con producto, unidad, cantidad, precio, tipo de IGV y memo cuando sea necesario.
5. Guardar como borrador y revisar los totales.
6. Registrar el documento cuando el comprobante sea válido.

El memo de una línea es información interna; no modifica precios, impuestos ni inventario. La unidad inicial debe corresponder a la unidad principal del producto; cualquier conversión debe estar configurada previamente.

Si una factura está vinculada a una orden que ya fue recibida, no debe generar una segunda entrada automática de inventario: la recepción es la fuente de la entrada física.

### 4.1 Registrar un gasto

Usar **Compras > Nuevo gasto** cuando el desembolso no corresponde a un producto del catálogo: alquiler del local, honorarios, servicios públicos, mantenimiento u otros gastos administrativos.

1. Seleccionar el proveedor y los datos del comprobante.
2. Elegir la categoría que describe la naturaleza del gasto.
3. Ingresar descripción, cantidad, valor unitario y tipo de IGV.
4. Guardar el borrador y registrarlo después de revisar los totales.

Las categorías permiten agrupar y analizar gastos; no representan artículos ni generan movimientos de almacén. Un flete comprado regularmente o que deba formar parte del catálogo puede crearse como producto no inventariable. Las categorías iniciales se cargan con `python manage.py seed`.

### 5. Gestionar cuentas por pagar y cuotas

Al registrar un documento se genera inicialmente una cuota por el total, con la fecha de vencimiento del documento. Antes de registrar pagos se puede reemplazar por un cronograma de varias cuotas.

1. Abrir el documento registrado.
2. Definir el cronograma de cuotas si el acuerdo con el proveedor es fraccionado.
3. Consultar **Cuentas por pagar** para revisar deuda, vencimientos y saldos.

No se debe modificar el cronograma después de aplicar pagos sin revisar primero las aplicaciones existentes.

### 6. Registrar o anular un pago

1. Desde el documento registrado seleccionar **Registrar pago**.
2. Indicar fecha, medio de pago, moneda, importe, referencia y las cuotas a aplicar.
3. Registrar el pago.

Un pago puede cubrir total o parcialmente la deuda. El documento cambia a no pagado, parcialmente pagado o pagado según sus aplicaciones. Si se anula el pago, se revierte el efecto sobre los saldos; el documento debe permanecer registrado.

### 7. Registrar costos adicionales

Usar costos adicionales para importes como flete, seguro, aduana u otros conceptos que se quieren analizar junto con una compra.

1. Abrir el documento de compra registrado.
2. Crear un costo adicional e indicar importe y método de distribución: por valor, por cantidad base o manual.
3. Confirmar la distribución sobre las líneas inventariables.

La distribución conserva el costo histórico asignado a cada línea. En la versión actual no recalcula automáticamente el costo valorizado del kardex ni las capas de inventario.

### 8. Consultar reportes

- **Historial de precios:** comparar las compras anteriores de un producto y proveedor.
- **Cuentas por pagar:** revisar documentos registrados, pagos y saldo pendiente.
- **Analítica de compras:** revisar gasto, proveedores, recepción, facturación, pagos, costos adicionales y variaciones de precio.

Los reportes se filtran por la empresa y sucursal activas. La exportación disponible actualmente es el CSV del resumen por proveedor.

## Estados y reglas de operación

| Entidad | Estados | Regla relevante |
| --- | --- | --- |
| Documento de compra | Borrador, Registrado, Cancelado | Solo el borrador puede editarse o eliminarse. Un documento con pago activo o costo adicional activo no debe cancelarse. |
| Orden de compra | Borrador, Aprobada, Cerrada, Cancelada | Solo una orden aprobada admite recepciones. |
| Recepción | Registrada, Cancelada | La anulación genera reversión de inventario. |
| Pago | Registrado, Anulado | El pago se aplica a cuotas y se puede anular para recalcular saldos. |
| Costo adicional | Distribuido, Anulado | Mantiene una distribución histórica por línea. |

## Controles ya incorporados

- Aislamiento de información por empresa y sucursal.
- Validación de pertenencia del almacén a la sucursal.
- Unicidad de comprobante por proveedor, tipo, serie y número.
- Validación de que una línea sea de producto **o** categoría de compra.
- Cantidades positivas, precios no negativos y tipo de cambio positivo.
- Movimientos de inventario reversables, en lugar de eliminar historial.
- Auditoría de transiciones relevantes.
- Actualización del precio de compra del producto únicamente al registrar el documento.

## Límites actuales y siguiente evolución

Estas funciones están deliberadamente fuera del alcance actual o requieren una fase posterior:

1. Antigüedad de deuda calculada estrictamente por cada cuota y no solo por el vencimiento general del documento.
2. Selección explícita de la línea de orden o recepción al facturar, especialmente cuando un producto se repite.
3. Aprobación de diferencias entre orden, recepción y factura (matching de tres vías).
4. Devoluciones a proveedor, notas de crédito y ajustes parciales.
5. Valorización de inventario y kardex con los costos adicionales distribuidos.
6. Conciliación bancaria, caja, asientos contables y diferencias de cambio para pagos.
7. Adjuntos de XML/PDF, validación de comprobantes y prevención reforzada de duplicados.
8. Permisos más específicos para aprobar, recibir, pagar, anular y consultar reportes.
9. Flujos de solicitud de compra, cotización, presupuesto y aprobación por monto.

## Verificación técnica

```bash
python manage.py migrate
python manage.py test apps.purchases --settings=config.settings_test
python manage.py makemigrations --check --dry-run
python manage.py check
```

En la revisión de cierre, las 56 pruebas del módulo de Compras pasaron y no se detectaron migraciones pendientes ni errores de configuración de Django.
