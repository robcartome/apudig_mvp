# API POS v1

Base URL: `/api/v1/pos/`.

Todos los endpoints requieren autenticacion, empresa y sucursal activas. El
servidor valida nuevamente el acceso y los permisos; los permisos enviados o
simulados por el cliente no se consideran confiables.

## Flujo operativo

1. Consultar `GET bootstrap/?register_id=<uuid>`.
2. Buscar articulos con `GET products/?register_id=<uuid>&search=<texto>`;
   la respuesta usa el precio y almacen predeterminados de la caja.
3. Si no existe sesion abierta, usar `POST sessions/open/`.
4. Buscar o crear el cliente mediante `GET|POST customers/`.
5. Registrar toda la venta con `POST sales/checkout/`.
6. Para facturacion diferida, solicitarla con `POST invoice-requests/` y emitir
   la consolidada con `POST consolidated-invoices/`.
7. Revisar el arqueo con `GET sessions/<session_id>/summary/` y cerrar mediante
   `POST sessions/<session_id>/close/`. El cierre se bloquea
   mientras existan operaciones o solicitudes de factura pendientes.

`sales/checkout/` es atomico: documento, inventario, ticket y pagos se confirman
juntos. `idempotency_key` debe ser un UUID estable generado por el dispositivo
para cada intento de venta. Repetir la solicitud con la misma clave devuelve la
venta original y no descuenta stock ni consume correlativos nuevamente.

Los precios unitarios enviados representan valor neto sin IGV. El backend
calcula subtotal, impuestos, descuentos y total. Cambiar el precio o la lista y
aplicar descuentos depende de permisos independientes.

La búsqueda de productos devuelve `units` con la unidad, factor de conversión y
precio de cada presentación. La cantidad comercial se conserva en el documento,
mientras `stock_quantity` se calcula en la unidad base. La emisión bloquea las
existencias por almacén y la anulación genera un movimiento inverso vinculado.

La condicion comercial se envia en `payment_condition` (`CASH` o `CREDIT`).
Las ventas al contado exigen cuadratura total. El credito requiere
`sell.pos.credit`, una condicion comercial no-contado y `due_date`; puede
registrarse sin adelanto o con pagos parciales. La respuesta informa
`payment_status`, `paid_amount` y `outstanding_amount`.
El vencimiento se conserva en `SalesDocument`, fuente comercial reutilizable
por impresion y por un futuro flujo de cobranza.

## Endpoints

| Metodo | Ruta | Permiso principal |
|---|---|---|
| GET | `bootstrap/` | `read.pos` |
| GET | `products/?register_id=&search=` | `read.pos` |
| POST | `sessions/open/` | `open.pos.cash` |
| POST | `sessions/<id>/movements/` | `manage.pos.cash_movements` |
| GET | `sessions/<id>/summary/` | `read.pos` |
| POST | `sessions/<id>/close/` | `close.pos.cash` |
| POST | `sales/checkout/` | `sell.pos` |
| GET | `sales/<id>/` | `read.pos` |
| GET | `sales/recent/?register_id=` | `reprint.pos.receipt` |
| POST | `sales/<id>/reprint/` | `reprint.pos.receipt` |
| POST | `sales/<id>/return/` | `refund.pos.sale` |
| POST | `sales/<id>/debit-note/` | `issue.pos.invoice` |
| POST | `sales/<id>/void/` | `void.pos.sale` |
| GET | `invoiceable-tickets/` | `read.pos` |
| POST | `invoice-requests/` | `consolidate.pos.invoice` |
| POST | `consolidated-invoices/` | `consolidate.pos.invoice` y `issue.pos.invoice` |
| GET | `customers/?search=` | `read.pos` |
| POST | `customers/` | `create.pos.customer` |

Una diferencia de efectivo solo puede cerrarse cuando el usuario posee
`authorize.pos.cash_difference`. La anulacion POS implementada en esta version
es para Notas de Venta de una sesion abierta. Facturas y boletas deben esperar
el flujo de anulacion fiscal.

El saldo de una venta a credito no se incorpora al efectivo esperado de caja.
La cobranza posterior del saldo es un flujo separado y no forma parte de esta
fase.

## Comprobantes e impresión

La respuesta de venta incluye las líneas necesarias para reconstruir el ticket,
la URL del formato A4, `electronic_status`, el mensaje del proveedor y
`qr_payload`. Este último solo se publica cuando factura o boleta ya tiene el
hash de firma electrónica; ApuDig no genera un QR fiscal aparente antes de la
respuesta real del proveedor.

La interfaz admite tickets de 58 y 80 mm. La reimpresión consulta operaciones
persistidas, vuelve a obtener sus datos desde el servidor y crea un `AuditLog`
con usuario, documento y ancho. El estado local `ISSUED` no implica aceptación
SUNAT: mientras no exista CDR se informa `PENDING`; las respuestas guardadas se
exponen como `ACCEPTED`, `REJECTED` o `ERROR`.

## Anulaciones, devoluciones y notas

Una Nota de Venta completada puede anularse únicamente mientras su sesión
original siga abierta, siempre que no haya sido consolidada. La anulación
cancela sus pagos y revierte todo el movimiento de inventario.

La devolución es una operación distinta y admite cantidades parciales. Exige
una caja actual abierta, una venta totalmente pagada, motivo, medio de
reembolso e `idempotency_key`. El servidor bloquea las líneas, impide devolver
más de lo vendido, devuelve existencias y descuenta el reembolso del arqueo.
Una devolución en efectivo se rechaza si el efectivo esperado de la caja no es
suficiente.

Para factura o boleta, la devolución emite una Nota de Crédito tipo `07`
relacionada; el documento original permanece emitido. Las Notas de Débito tipo
`08` registran cargos adicionales, no mueven inventario y también son
idempotentes. En ambos casos la aceptación fiscal continúa dependiendo del
proveedor electrónico y no se generan asientos contables.

El resumen de sesión separa fondo inicial, ventas en efectivo, otros medios,
ingresos, salidas, efectivo esperado y operaciones pendientes. La apertura y
el cierre aceptan conteo por denominaciones; el cierre también registra la
conciliación declarada por cada medio no efectivo y genera un resumen imprimible.

## Facturacion consolidada

Los tickets deben ser Notas de Venta POS emitidas y pagadas, del mismo cliente
con RUC, sucursal, moneda y fecha operativa. La factura consolidada se emite sin
movimiento adicional de inventario y conserva enlaces a todos los documentos
origen. Un ticket no puede facturarse dos veces.

Los errores de dominio utilizan el formato:

```json
{
  "code": "PAYMENT_MISMATCH",
  "detail": "Los pagos no cuadran con el total de la venta."
}
```

## Interfaz web

La estacion de venta esta disponible en `/pos/`. Usa esta API con la sesion
Django activa, conserva los calculos autoritativos en el servidor y adapta el
flujo a escritorio, tablet y movil. En pantallas pequenas, el panel de cobro se
presenta como una bandeja inferior y todos los controles operativos mantienen
un area tactil minima.
