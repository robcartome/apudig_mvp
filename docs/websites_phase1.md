# Fase 1: fundaciones del sistema de sitios web

## Alcance implementado

La app `websites` conserva la relaciÃ³n 1:1 entre empresa y sitio e incorpora:

- identidad operativa del sitio (`slug`, locale, zona horaria y moneda);
- autorÃ­a y fecha de publicaciÃ³n;
- dominios tipados y estados de verificaciÃ³n;
- challenge DNS cuyo valor se entrega una vez y se almacena como SHA-256;
- `WebsiteSettings` 1:1 para identidad pÃºblica, contacto, colores y SEO bÃ¡sico;
- permisos `read.website`, `manage.website` y `manage.website.domains`;
- endpoints CMS limitados siempre a la empresa del JWT.

No incluye pÃ¡ginas, secciones, menÃºs, medios, productos publicados, verificaciÃ³n DNS automÃ¡tica ni activaciÃ³n de dominios desde la API.

## Endpoints

### PÃºblico

`GET /api/v1/storefront/resolve/?hostname={hostname}`

Solo resuelve un dominio `ACTIVE`, con `verified_at`, perteneciente a un website `PUBLISHED` y una empresa activa. Devuelve identidad, canonical, locale, moneda, tema y contacto. Nunca devuelve `company_id`.

### CMS autenticado

| Endpoint | Permiso |
| --- | --- |
| `GET /api/v1/websites/current/` | `read.website` |
| `PATCH /api/v1/websites/current/` | `manage.website` |
| `GET /api/v1/websites/current/settings/` | `read.website` |
| `PATCH /api/v1/websites/current/settings/` | `manage.website` |
| `GET /api/v1/websites/current/domains/` | `read.website` |
| `POST /api/v1/websites/current/domains/` | `manage.website.domains` |

`current` se deriva exclusivamente de la empresa autorizada del JWT. No existe selector `company_id` en URL, query ni body. Un dominio nuevo queda `PENDING`, nunca primario, y la respuesta de creaciÃ³n contiene el token DNS una sola vez. Duplicados devuelven `409 DOMAIN_CONFLICT` y hosts reservados devuelven `400`.

## Variables de entorno

```text
WEBSITE_PLATFORM_DOMAIN=apudig.com
WEBSITE_RESERVED_SUBDOMAINS=www,web,admin,api,media,status
```

Los labels reservados no pueden registrarse como tiendas dentro del dominio de plataforma. `www` de un dominio personalizado sigue tratÃ¡ndose como un hostname independiente.

## Despliegue

1. Respaldar la base de datos.
2. Desplegar el backend y ejecutar `python manage.py migrate`.
3. Crear o revisar el `Website` desde Django Admin.
4. Registrar el dominio. La API lo crea pendiente y entrega el challenge DNS.
5. Verificar externamente propiedad/DNS. Hasta implementar la automatizaciÃ³n de la Fase 6, un administrador debe establecer `verified_at`, `ACTIVE` e `is_primary` solo después de esa comprobaciÃ³n.
6. Configurar el wildcard y certificado en Vercel/DNS.
7. Desplegar Next.js con las variables server-only documentadas en su `.env.example`.
8. Probar host conocido, desconocido, reservado y acceso administrativo.

## Rollback

Revertir primero el frontend para detener rewrites y despuÃ©s el backend. La migraciÃ³n puede volver a `websites 0001`, pero elimina `WebsiteSettings`, campos de fundaciÃ³n y permisos de website; requiere respaldo previo. Los modelos base `Website` y `WebsiteDomain` de Fase 0 permanecen.

## Seguridad y operaciÃ³n

- Django sigue siendo la autoridad sobre tenant y publicaciÃ³n.
- Un token firmado para una empresa sin acceso real es rechazado.
- El challenge DNS nunca se almacena en claro.
- Los logs públicos incluyen `request_id`, `website_id` y hostname, sin JWT ni datos personales.
- No existe website por defecto: host desconocido o no activo responde `404`.
