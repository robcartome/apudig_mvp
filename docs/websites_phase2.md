# APUDIG Web — Fase 2: CMS de páginas por bloques

## Alcance entregado

La Fase 2 incorpora páginas editables multiempresa con bloques versionados. El borrador (`WebsitePage` + `WebsiteSection`) está físicamente separado de la revisión pública inmutable (`WebsitePageRevision`), por lo que guardar cambios nunca altera el storefront hasta publicar.

Bloques permitidos inicialmente:

- `hero.v1`
- `image_text.v1`
- `benefits.v1`
- `contact.v1`

El backend rechaza tipos, versiones, campos, URLs y marcado ejecutable que no estén en la lista permitida. El frontend renderiza propiedades React y no usa HTML arbitrario.

## API CMS

Todas las rutas CMS se limitan a la empresa del JWT activo:

- `GET|POST /api/v1/websites/current/pages/`
- `GET|PATCH|DELETE /api/v1/websites/current/pages/{id}/`
- `PUT /api/v1/websites/current/pages/{id}/sections/`
- `POST /api/v1/websites/current/pages/{id}/preview-token/`
- `POST /api/v1/websites/current/pages/{id}/publish/`

El reemplazo de bloques y la publicación requieren `expected_version`. Una edición concurrente devuelve `409` con `code=VERSION_CONFLICT`.

Permisos:

- `read.website`: consultar páginas.
- `manage.website`: crear y editar borradores, ordenar bloques y generar vista previa.
- `publish.website`: publicar una revisión. No se concede implícitamente a editores.

## API pública y vista previa

`GET /api/v1/storefront/sites/{hostname}/pages/{slug}/` devuelve exclusivamente la revisión publicada correspondiente a un dominio activo y verificado. Un borrador no publicado responde `404`.

La vista previa usa `preview_token`, firmado y ligado al sitio, página y versión de borrador. Expira según `WEBSITE_PREVIEW_TOKEN_TTL` (900 segundos por defecto) y deja de ser válido cuando cambia el borrador.

## Publicación e invalidación

La publicación bloquea la página, verifica la versión, valida nuevamente todos los bloques, crea una instantánea inmutable y actualiza el puntero público dentro de una sola transacción.

Después del commit se envía un webhook opcional a `STOREFRONT_REVALIDATE_URL` con etiquetas específicas del sitio, página y host. Django autentica con `STOREFRONT_REVALIDATE_SECRET`; Next.js valida el mismo secreto y sólo acepta formatos de etiquetas permitidos.

Variables:

```env
WEBSITE_PREVIEW_TOKEN_TTL=900
STOREFRONT_REVALIDATE_URL=http://localhost:3000/api/revalidate
STOREFRONT_REVALIDATE_SECRET=un-secreto-largo
```

## Operación

1. Aplicar `python manage.py migrate`.
2. Configurar el mismo secreto de revalidación en backend y frontend.
3. Asignar `publish.website` únicamente a roles publicadores. La migración lo agrega a roles llamados `ADMIN` o `SUPERUSER` si ya existen.
4. Abrir `/admin/website/pages`; la página de inicio se crea automáticamente para sitios existentes y nuevos.

## Verificación realizada

- Django system check sin incidencias.
- Migraciones sin cambios pendientes.
- Suite `apps.websites.tests`: 18 pruebas aprobadas.
- Frontend: lint sin advertencias y 8 pruebas de tenant/CMS aprobadas.
- Build Next.js de producción aprobado con Webpack y concurrencia limitada a dos workers.
