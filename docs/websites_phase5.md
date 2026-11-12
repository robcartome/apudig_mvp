# Sitios web — Fase 5

La Fase 5 incorpora un carrito local por website y una solicitud de cotización
por WhatsApp. No crea ventas, pedidos, clientes ni reservas de stock en el ERP.

## Contrato público

```http
POST /api/v1/storefront/sites/{hostname}/cart/quote/
Content-Type: application/json

{
  "lines": [
    {"product_id": "uuid", "quantity": 2}
  ]
}
```

Se aceptan como máximo 50 productos distintos y cantidades enteras de 1 a 999.
El navegador no envía un precio confiable. Django vuelve a resolver el dominio,
consulta `WebsiteProduct` publicados y recalcula precio, subtotal y
disponibilidad desde las fuentes configuradas en Fase 4.

La respuesta contiene:

- líneas `ACTIVE`, `REMOVED` u `OUT_OF_STOCK`;
- total calculado sólo con líneas activas;
- `quote_id`, vigencia y snapshot firmado `quote_token`;
- `has_changes` y `can_submit` para impedir mensajes desactualizados.

Un producto inexistente, retirado o perteneciente a otro tenant se devuelve
como `REMOVED` sin nombre, SKU, precio ni otro dato que permita inferirlo.

## Rate limit y vigencia

- `STOREFRONT_QUOTE_RATE` controla el límite por hostname/IP; valor recomendado
  inicial: `20/min`.
- `STOREFRONT_QUOTE_TTL` controla la vigencia en segundos; valor inicial: `900`.
- Las respuestas de cotización y el proxy Next usan `no-store`.

En producción con más de una instancia Django, el cache de throttling debe ser
compartido (por ejemplo Redis). El cache local sólo limita por proceso.

## Persistencia frontend

El carrito se guarda bajo
`apudig:storefront-cart:v1:{website_id}`. El payload incluye versión y
`website_id`; un valor de otro sitio, versión desconocida o forma inválida se
descarta. Se guardan snapshots visuales, pero nunca se usan para construir el
total final.

El mensaje WhatsApp contiene referencia corta, SKU, cantidad, precio vigente,
subtotales y total cotizado. No incluye el token firmado, secretos, datos de
usuario ni PII. Se etiqueta expresamente como solicitud de cotización.

## Analítica

Los eventos locales `apudig:analytics` incluyen sólo nombre de evento,
`website_id`, `product_id`, cantidades, número de líneas y estado de cambios.
No incluyen nombre, teléfono, dirección, texto del mensaje ni datos del cliente.

## Rollback

No hay migración de base de datos. El rollback consiste en retirar el endpoint,
el Route Handler y el provider. Los carritos ya persistidos son namespaced y
pueden quedar sin uso; una versión futura debe incrementar el número de esquema
si cambia su estructura.

## Verificación

```powershell
python manage.py check
python manage.py test apps.inventory.tests.test_catalog_api apps.websites.tests --keepdb --noinput
```

