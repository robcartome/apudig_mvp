# Sitios web — Fase 3

La Fase 3 incorpora identidad visual, biblioteca de medios, menús publicables,
dominio canónico y metadatos SEO con aislamiento por empresa.

## Migración

Ejecutar:

```powershell
python manage.py migrate
```

La migración `0004_theme_media_menus_seo_phase_3` agrega los modelos de medios
y menús, amplía `WebsiteSettings`, crea el permiso `manage.website.media` y
genera menús iniciales para los sitios existentes. Los roles `ADMIN` y
`SUPERUSER` reciben el nuevo permiso si ya existen durante la migración.

## Contratos privados

Todos los endpoints se resuelven desde la empresa seleccionada en el JWT:

- `GET/PATCH /api/v1/websites/current/settings/`
- `POST /api/v1/websites/current/domains/{id}/primary/`
- `GET/POST /api/v1/websites/current/media/`
- `PATCH/DELETE /api/v1/websites/current/media/{id}/`
- `GET/POST /api/v1/websites/current/menus/`
- `GET/PATCH /api/v1/websites/current/menus/{id}/`
- `PUT /api/v1/websites/current/menus/{id}/items/`
- `POST /api/v1/websites/current/menus/{id}/publish/`

La edición de borradores usa `draft_version` como control optimista. Publicar
requiere `publish.website`; gestionar medios requiere `manage.website.media`.
Los IDs de páginas y medios de otra empresa se rechazan aunque sean válidos.

## Contratos públicos

- `GET /api/v1/storefront/resolve/?hostname=...` devuelve tema, contacto,
  navegación publicada, SEO y dominio canónico.
- `GET /api/v1/storefront/sites/{hostname}/manifest/` devuelve las páginas
  publicadas necesarias para sitemap y robots.

Un alias verificado puede resolver el sitio, pero el campo
`canonical_hostname` siempre apunta al dominio primario.

## Medios y almacenamiento

Los archivos se validan y optimizan con el mismo pipeline de imágenes del
catálogo. Las claves se guardan bajo `websites/{website_id}/media/` en el
almacenamiento R2/S3 configurado. La deduplicación por checksum es local al
sitio; nunca comparte una referencia entre empresas.

Se requieren las variables de almacenamiento ya documentadas para imágenes de
producto (`R2_ENDPOINT_URL`, credenciales, bucket y URL pública). Si falta la
configuración, la subida falla de forma explícita y no crea un registro huérfano.

## Publicación e invalidación

Editar un menú no cambia el storefront. `publish` guarda una instantánea
inmutable de sus enlaces y registra la versión publicada. Al confirmar la
transacción se envían las etiquetas de revalidación del sitio y sus hosts.

## Rollback

Antes de revertir la migración, exportar o respaldar menús y medios. La
reversión elimina sus tablas y los campos de tema/SEO agregados a settings; no
borra objetos ya cargados en el bucket, que deben retirarse mediante el proceso
de limpieza del almacenamiento.

## Verificación

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.websites.tests --keepdb --noinput
```

