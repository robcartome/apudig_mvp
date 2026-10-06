# Límites de subida de imágenes de productos

## Estado verificado

El formulario Django recibe hasta tres imágenes en una sola petición `multipart/form-data`.
El frontend intenta producir como máximo 1.2 MiB por imagen y bloquea el envío cuando
la suma de los archivos seleccionados supera 4 MiB. El backend mantiene un límite de
5 MiB por archivo.

El repositorio no contiene la configuración productiva del servidor Django, proxy,
WAF o proveedor. Los contenedores incluidos usan `runserver` directamente. Por ello,
el componente exacto que produjo el 413 no puede identificarse únicamente desde este
repositorio.

La configuración local solo evidencia:

- `media.apudig.com` detrás de Cloudflare para servir objetos R2;
- `apudig.vercel.app` como origen CORS permitido;
- ninguna configuración Nginx, Caddy, Traefik, Gunicorn o plataforma Django.

Que el frontend esté permitido desde Vercel no demuestra que el POST de Django pase
por una Vercel Function. Debe verificarse el hostname exacto mostrado en Network para
el POST `/inventory/products/<uuid>/edit/`.

## Presupuesto de la petición

Presupuesto conservador para el formulario completo:

| Componente | Máximo esperado |
| --- | ---: |
| Tres imágenes optimizadas | 3.6 MiB |
| Campos y multipart overhead | < 0.4 MiB |
| Límite preventivo frontend | 4 MiB |
| Límite recomendado de proxy/origen | 8 MiB |

El margen hasta 8 MiB permite variaciones de multipart y clientes compatibles que no
generen exactamente el mismo tamaño, sin aceptar originales de decenas de megabytes.

## Cómo localizar el emisor del 413

1. Abrir las herramientas del navegador y seleccionar la petición POST fallida.
2. Registrar `Request URL`, `Status`, `Server`, `Via`, `X-Vercel-Id`, `CF-Ray` y el
   cuerpo de respuesta.
3. Buscar la misma hora y ruta en logs del proveedor, proxy y aplicación Django.
4. Si no existe entrada en logs Django, el rechazo ocurrió antes de la aplicación.
5. Confirmar el tamaño real del request en Network; no usar el tamaño del objeto WebP
   almacenado en R2, porque ese objeto se crea después de recibir y procesar el POST.

Indicadores frecuentes:

- `server: nginx`: revisar `client_max_body_size`.
- `x-vercel-id` o `FUNCTION_PAYLOAD_TOO_LARGE`: límite de Vercel Function.
- `server: cloudflare` y página de error Cloudflare: revisar el límite de upload de la zona.
- Respuesta Django personalizada o entrada en logs Django: revisar límites de aplicación.

## Configuración recomendada

Si existe Nginx delante de Django, configurar el límite solo en el servidor o location
correspondiente y recargar la configuración:

```nginx
client_max_body_size 8m;
```

El servidor WSGI/ASGI y cualquier balanceador anterior deben aceptar al menos el mismo
tamaño. Si Django corre dentro de una Vercel Function, su límite de request no se puede
elevar a 8 MiB; se debe mantener el cuerpo por debajo de 4.5 MB o rediseñar el upload.

No se recomienda una subida directa anónima a R2. Una futura carga directa requeriría
URLs firmadas de duración corta, autenticación, autorización por empresa, validación de
key y una confirmación backend antes de asociar el objeto al producto.

## Prueba de aceptación

- Subir una, dos y tres imágenes desde iPhone y Android.
- Confirmar en Network que el request completo no supera 4 MiB.
- Confirmar respuesta 302/200 de Django, sin 413.
- Confirmar que se crean imagen y thumbnail en R2.
- Repetir con JavaScript deshabilitado: el backend debe rechazar cada archivo mayor a
  5 MiB, aunque el proxy puede aplicar antes su límite total.
