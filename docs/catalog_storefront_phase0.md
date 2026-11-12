# Fase 0: seguridad multiempresa del catálogo

## Alcance implementado

Esta fase separa el catálogo público de los endpoints privados de inventario y hace obligatorio un tenant resuelto por dominio registrado.

No incluye CMS, páginas, carrito, pedidos ni automatización DNS/Vercel. En esta fase, un producto es publicable si pertenece a la empresa del website y `Product.active=True`. La selección individual mediante `WebsiteProduct` queda para la fase de storefront/CMS.

## Modelo mínimo de tenant

- `Website`: relación uno a uno con `Company` y estado `DRAFT`, `PUBLISHED` o `SUSPENDED`.
- `WebsiteDomain`: hostname globalmente único, estado y fecha de verificación.
- Solo resuelve un dominio con `status=ACTIVE`, `verified_at` informado, website publicado y empresa activa.
- Los hostnames se normalizan a minúsculas/IDNA y no aceptan protocolo, puerto, ruta ni dirección IP.

El hostname es un selector público validado, no una autorización. Nunca se acepta `company_id` del navegador para construir el queryset.

## Endpoints

### Storefront público

```text
GET /api/v1/storefront/resolve/?hostname={hostname}
GET /api/v1/storefront/sites/{hostname}/products/?search=&brand=&category=&limit=&offset=
GET /api/v1/storefront/sites/{hostname}/products/{uuid}/
```

Respuestas:

- `200`: dominio activo y recurso dentro de su empresa.
- `400`: falta el hostname en `resolve` o falta `site` en el contrato legado.
- `404`: dominio desconocido/inactivo o producto fuera del tenant.

Las respuestas públicas omiten `price_purchase`, códigos/proveedores, listas internas de precios, stock total y stock por almacén.

### Compatibilidad temporal

```text
GET /api/v1/catalog/products/?site={hostname}
GET /api/v1/catalog/products/{uuid}/detail/?site={hostname}
```

Estos endpoints están deprecados en OpenAPI. Ya no funcionan sin `site` y usan el mismo resolver/serializador seguro que el storefront.

### Inventario privado

```text
GET /api/v1/products/
GET /api/v1/products/{uuid}/
GET /api/v1/catalog/private/products/
GET /api/v1/catalog/private/products/{uuid}/detail/
```

Requieren:

1. usuario autenticado;
2. `company_id` en token/sesión;
3. acceso actual del usuario a empresa/sucursal;
4. permiso `read.inventory.products` cuando el módulo está configurado.

Si todavía no existen permisos del módulo `inventory.products`, se conserva el acceso legado para usuarios con contexto autorizado, siguiendo el comportamiento de `user_has_company_permission`. En cuanto el permiso se configure, el acceso es deny-by-default salvo ADMIN/superusuario o rol autorizado.

Un recurso de otra empresa responde 404 porque el queryset ya está filtrado.
Una solicitud sin credenciales responde 403 con el autenticador JWT actual; una
credencial Bearer inválida responde 401. Normalizar el challenge HTTP del
autenticador queda fuera de esta fase para no cambiar globalmente la autenticación.

## Compatibilidad Next.js

`ad_frontend/src/services/productsService.js` usa el endpoint storefront y obtiene el dominio de:

1. `NEXT_PUBLIC_STOREFRONT_HOST`, si está configurado; o
2. `window.location.hostname`.

El override es útil para localhost y previews. No contiene un `company_id` y Django siempre vuelve a resolverlo contra `WebsiteDomain`.

## Migración y despliegue

1. Desplegar backend con la migración `websites.0001_initial`.
2. Crear un `Website` publicado para la empresa actual.
3. Crear `WebsiteDomain` para `apudig.vercel.app` o el hostname usado por el frontend, inicialmente verificado y luego activo.
4. Verificar manualmente resolve, lista y detalle.
5. Configurar `NEXT_PUBLIC_STOREFRONT_HOST` únicamente si el hostname del navegador no corresponde al dominio registrado (localhost/preview).
6. Desplegar el frontend actualizado.
7. Confirmar que una solicitud sin tenant falla y que el catálogo muestra solo la empresa configurada.

No se incluye una migración de datos porque el repositorio no identifica de forma inequívoca qué `Company` corresponde a Tolentino. La asociación debe hacerse explícitamente durante el despliegue.

## Rollback

Rollback seguro de aplicación:

1. Revertir frontend y backend al release anterior de forma coordinada.
2. No eliminar inmediatamente las tablas `websites`/`website_domains`; son inertes para el código anterior y preservan la configuración.
3. Si se requiere rollback de esquema, ejecutar `migrate websites zero` solo después de retirar el código que importa la app y respaldar los registros.

Advertencia: volver al backend anterior reabre la fuga multiempresa. Es preferible mantener el backend seguro y corregir/configurar el consumidor antes que restaurar el contrato inseguro.

## Verificación automatizada

Las pruebas cubren:

- empresas A/B y productos distintos;
- tenant ausente, válido y desconocido;
- detalle cruzado, búsqueda, categoría y marca;
- producto inactivo;
- campos públicos privados ausentes;
- autenticación, token sin empresa y token firmado para empresa no autorizada;
- aplicación del permiso de inventario;
- normalización y validación de dominios.
