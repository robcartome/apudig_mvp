# Administración de Website y dominios

Fecha: 16/11/2026. Ajuste de administración B1–B3; no inicia B4.

## Uso en la base local

La inspección previa de `apudig_mvp` en localhost:5432 fue de solo lectura: migraciones Website 0001–0009 aplicadas, 14 tablas compatibles y cinco permisos existentes. No había Websites ni dominios. Este ajuste no requiere migraciones y no crea registros automáticamente en esa base.

1. Entrar a Django en `http://localhost:8000/`, iniciar sesión y seleccionar expresamente la empresa.
2. Abrir **Administración → Website y dominios**, o `http://localhost:8000/management/websites/`.
3. Pulsar **Crear Website de esta empresa**. Se crea un único Website DRAFT, sin publicación, productos ni modificaciones fiscales. El GET no crea datos.
4. Registrar el hostname sin esquema/puerto/ruta, por ejemplo `tienda.localhost` para un desarrollo local autorizado. Se normaliza y queda PENDING.
5. El personal APUDIG (superusuario) comprueba el control fuera de la pantalla y registra evidencia mediante **Registrar comprobación de control**. Para un hostname local se documenta su aprovisionamiento explícito. Esto es una atestación manual auditada, no una comprobación DNS automática. No se debe registrar evidencia de control que no se haya realizado.
6. Un usuario con gestión de dominios activa el dominio VERIFIED y después puede elegirlo como principal. La activación no publica el Website. Desactivar elimina su condición de principal y revoca su evidencia; requiere otra comprobación para reactivarlo.
7. Entrar al editor Next con la misma empresa, guardar y publicar contenido. Para entrar desde localhost:3000, usar `WEBSITE_DEV_HOSTNAME=tienda.localhost` con `npm.cmd run dev`. Los datos se leen de Django y PostgreSQL, sin fallback demo.

Para desarrollo local permanente, configurar ambas URLs Next (`NEXT_PUBLIC_API_V1_URL` y `WEBSITE_API_V1_URL`) con `http://127.0.0.1:8000/api/v1` y los orígenes locales correspondientes en CORS. Reiniciar Next después de cambiar variables. No se modificaron `.env` ni credenciales en esta entrega. La verificación DNS automatizada sigue como dependencia operacional futura.

## Permisos de usuarios

El flujo continúa siendo el ERP existente: configurar permisos de un rol (personal autorizado para roles globales), seleccionar empresa en `/management/users/`, abrir el usuario, pestaña **Roles**, asignar ese rol y guardar. La pantalla muestra una explicación de las cinco capacidades Website y un enlace para el personal APUDIG que configura roles.

| Código | Operación |
|---|---|
| read.website | Consultar Website |
| manage.website | Crear Website/borradores y editar contenido |
| publish.website | Publicar contenido guardado |
| manage.website.media | Gestionar imágenes |
| manage.website.domains | Registrar/activar/desactivar/elegir dominio principal |

No se creó un permiso paralelo por usuario ni otro login. Se revalidan membresía vigente, empresa/sucursal activa y grants ERP. Un rol sin acceso actual a la empresa no conserva autorización. Registrar una verificación manual exige además superusuario APUDIG; un administrador de empresa no puede autoatestiguar control de dominios.

## Django Admin

Los modelos Website aparecen en `/admin/` para superusuarios activos con acceso staff. Es una **consulta técnica de solo lectura**: no hay altas, cambios, acciones masivas ni borrado directo, incluidas revisiones y configuración editorial. El listado enlaza a la administración funcional. La gestión de contenido sigue utilizando los servicios transaccionales del editor y su ETag; no se habilita un segundo CRUD que los eluda.

## Archivos

- Nuevos: `apps/websites/admin.py`, `domain_services.py`, `forms.py`, `views.py`, `urls.py`, tag `templatetags/website_access.py`, pruebas `tests/test_management.py`.
- Nuevas plantillas: `templates/websites/management.html` y `templates/admin/websites/change_list.html`.
- Integración: `config/urls.py`, navegación en `templates/admin_panel/_tabs.html` y `templates/components/sidebar.html`, ayuda de roles en `templates/admin_panel/user_detail.html`.
- Ajuste de prueba de usuarios: el enlace al panel general se compara como `href` exacto, para no confundir `/management/websites/` con `/management/`. Se conserva la denegación HTTP403 de gestión de usuarios al administrador de sucursal.
- Sin cambios de modelos, migraciones, autenticación, frontend, productos o servicios comerciales.

Cada mutación bloquea el agregado Website (la creación bloquea Company), vuelve a comprobar permisos y guarda el evento en AuditLog dentro de la misma transacción. Las consultas y dominios están acotados a la empresa activa; no se toma company_id del formulario como autorización. Los formularios usan sesión existente, POST y CSRF; las respuestas no se cachean. Los dominios no se borran físicamente.

## Verificación

Resultado final: **133 pruebas correctas en PostgreSQL** (113 Website, incluidas 11 nuevas de administración, y 20 de administración de usuarios/empresas). Django check y makemigrations --check correctos, sin migraciones nuevas. La base de test fue eliminada por el runner al concluir.

Las pruebas cubren creación explícita/idempotente, borrador no publicado, normalización, activación forjada, permisos y ownership, CSRF, atestación y auditoría, revocación al desactivar, cambio de principal, inspección Admin y asignación de roles desde gestión de usuarios. Se ejecutan también las pruebas Website existentes y la regresión de administración de empresas/usuarios en PostgreSQL `test_apudig_website_admin_tests`, separada de los datos habituales.

Se usa StaticFilesStorage únicamente en memoria del runner de regresión para no depender de un manifiesto collectstatic inexistente en tests. El primer intento de regresión encontró ocho errores por ese manifiesto en tests de usuarios; no se cambió el almacenamiento de la aplicación para resolverlos. La ejecución final usa también MD5PasswordHasher solo en memoria del runner para los usuarios sintéticos de esa base de test; la seguridad de la aplicación y la base habitual no se modifican. El resultado final se conserva en [website-management-tests.json](website-management-tests.json).

No se declara validación visual de navegador ni verificación DNS/R2 real. No hubo commits, push o despliegue. No se aplicaron migraciones ni se sembraron datos en `apudig_mvp`: el primer Website se crea al elegir la empresa y confirmar su creación en la pantalla nueva.
