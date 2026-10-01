# Contrato de precios, impuestos y costos

## Semantica canonica

- `Product.price_sale`, `Product.price_purchase`, `ProductUnit.sale_price`,
  `ProductUnit.purchase_price` y `ProductPrice.amount` son precios comerciales
  finales, con impuesto incluido cuando la afectacion del producto lo exige.
- `Sales*Line.unit_price` y `Purchase*Line.unit_price` son valores unitarios
  netos. Cada linea conserva afectacion, tasa, descuentos e importes calculados
  como snapshot; una tasa futura no modifica documentos existentes.
- `Product.last_purchase_unit_value` es el ultimo valor neto de compra en moneda
  base. `Product.inventory_unit_cost` es el costo promedio vigente y puede
  incorporar costos de importacion o cargos distribuidos.
- `MovementDetail.unit_price` siempre representa costo de inventario en moneda
  base. `cost_source` identifica si proviene de compra, promedio, carga manual o
  informacion historica no clasificable.

## Compatibilidad de catalogo

La API conserva los campos existentes (`price_sale`, `price_purchase` y
`price_list[].amount`) y sus valores comerciales. Agrega `price_includes_tax`,
`tax_affectation` y `tax_rate`, de modo que Next.js no necesita cambiar la
forma en que muestra precios y puede adoptar los metadatos tributarios de forma
gradual.

## Operacion y migracion

Las tasas nuevas se configuran en `TaxRate` con vigencia. La configuracion
operativa anterior queda como fallback. Antes y despues de desplegar se debe
ejecutar:

```bash
python manage.py audit_pricing_tax
python manage.py migrate
python manage.py audit_pricing_tax
```

La migracion inicializa el costo neto desde el precio de compra comercial y la
tasa configurada. Los movimientos previos quedan marcados como `LEGACY`: no se
reescriben porque no existe evidencia suficiente para reconstruir el costo
historico exacto. Deben revisarse con kardex y comprobantes antes de cualquier
backfill contable.
