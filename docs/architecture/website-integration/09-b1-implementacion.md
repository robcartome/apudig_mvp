# 09 — Entrega B1: dominio Website y resolución segura de empresa

Fecha: 15/11/2026, America/Lima. Alcance: exclusivamente B1. Código preparado para revisión; sin commits, push, despliegue ni cambios frontend.

## Resultado y estado de aceptación

Se incorporó el dominio Website con esquema histórico conciliado en PostgreSQL de integración aislado, autorización específica que deniega por defecto, resolución interna por dominio y descubrimiento administrativo. No se implementaron APIs de edición, publicación, preview, media, catálogo comercial o cotización.

Las **48 pruebas específicas de B1 pasan en PostgreSQL 18.1**, incluidas dos pruebas de compatibilidad de nomenclatura añadidas después de la entrega inicial. La suite global no está verde: la comparación completa previa al ajuste de nombres encontró en el commit base y B1 los mismos 83 fallos y 35 errores. No se introdujeron nuevos casos fallidos en esa comparación. B1 queda implementada y validada de forma aislada, lista para revisión; no se declara aceptación global del ERP ni habilitación en la base habitual. El detalle reproducible de casos está en [b1-regresion.json](b1-regresion.json).

No se consultaron ni migraron los datos de la base habitual. La conciliación demostrada corresponde a la instancia de integración, no acredita el historial de otra instalación. Antes de habilitar B1 en una base existente hay que ejecutar la revisión de esquema/historial de 04 sobre esa base autorizada.

## Ramas, versiones y preservación

| Elemento | Evidencia |
|---|---|
| Backend | `apudig_mvp`, rama `develop`, base `c8296b7` |
| Frontend | `ad_frontend`, rama `mvp_website`, `57c212a`; sin modificaciones |
| Fuente histórica | `websites_v0`, commit `a9d3a3a`, recuperada mediante lectura de objetos Git; sin merge/cherry-pick/checkout |
| Versiones reales | Python 3.12.1, Django 5.2.19, DRF 3.18.3, psycopg 3.3.8, PyJWT 2.15.1 |
| PostgreSQL de pruebas | PostgreSQL 18.1; instancia temporal independiente, vinculada solo a loopback; datos sintéticos |
| `.gitignore` previo | Conservado; hash Git antes y después `3b726931da3d79b084bc803c3b5fae7d3039e612` |
| Documentación B0 previa | Ocho documentos preservados; notas de estado B1 añadidas solo donde corresponde |

No se actualizaron dependencias. El arranque inicial de initdb no pudo ejecutarse dentro del sandbox de Windows; se utilizó la elevación aprobada para iniciar exclusivamente la instancia temporal. No se usaron credenciales del servidor PostgreSQL habitual ni se modificó su servicio.

## Conciliación y migraciones

1. Configuración efectiva habitual: motor PostgreSQL y host local, pero sin base identificada como integración. No se la consideró autorización para migrar.
2. Se creó una instancia PostgreSQL temporal independiente y la BD `apudig_b1_integration`. La autenticación trust quedó limitada a esa instancia local con datos de prueba; no es una configuración para producción.
3. Antes de recuperar modelos se validó el grafo fuente y se aplicó el baseline ERP a esta base vacía: **141 migraciones**, sin historial ni tablas Website.
4. Las hojas de dependencias coincidieron: companies `0015_companybranding_show_company_name_with_logo`, users `0005_useroperationalflags_can_correct_pos_payment`, inventory `0022_product_company_barcode_index`.
5. En la entrega inicial se recuperaron **0001–0006 byte a byte**, comprobadas contra a9d3a3a. El ajuste posterior de nomenclatura conserva las operaciones y adapta nombres, referencias y dependencias como se detalla al final de este informe.
6. Se añadieron dos migraciones incrementales nuevas, revisadas con migrate --plan y comprobación de ausencia de cambios de modelos pendientes.
7. En integración se aplicaron las ocho migraciones nuevas para ese baseline: seis recuperadas + websites0007 + users0006. Auditoría posterior: **12 tablas del dominio**, con columnas, índices, restricciones y FKs coherentes con el historial registrado.
8. Las pruebas ensayan también la incorporación sobre registros ERP existentes y el rechazo de dominios históricos incompatibles. No se usa --fake ni se reescribe el recorder como solución de despliegue.

| Migración | Decisión / aplicación |
|---|---|
| websites 0001–0006 | Fuentes recuperadas y aplicadas únicamente en integración/test; ajuste posterior de nombres en 0003/0004, sin cambiar operaciones |
| `websites/0007_website_editorial_revision_and_more.py` | Contador/referencia futura de publicación y restricciones de dominios; RunPython aborta si hay datos históricos incompatibles, sin corregirlos silenciosamente |
| `users/0006_alter_permission_action_name.py` | Añade la opción publish/Publicar ya utilizada por permisos históricos; no modifica grants o decisiones de permisos del ERP |
| Base habitual / producción | Ninguna migración aplicada ni historial inspeccionado en esta intervención |

## Archivos recuperados

Desde a9d3a3a:

- `apps/websites/__init__.py`.
- `apps/websites/models.py`, adaptado exclusivamente para B1.
- `apps/websites/blocks.py`, dependencia de validación de los modelos de esquema recuperados, sin API ni editor activados.
- `apps/websites/migrations/__init__.py` y 0001–0006; posteriormente se renombraron 0003/0004 y se actualizó la dependencia de 0005, conservando sus operaciones.

No se recuperaron `signals.py`, `admin.py`, servicios de publicación, integración de media, views/URLs históricas ni reemplazos de catálogo/inventario. La nueva AppConfig no importa señales: crear una empresa o Website no publica nada ni crea un CMS mediante efectos secundarios. Las entidades adicionales se incorporaron para conservar consistente la cadena de esquema, no para activar B2/B4.

## Archivos creados

| Ubicación | Archivos / responsabilidad |
|---|---|
| `apps/websites/` | `apps.py`: registro sin señales; `permissions.py`: autorización actual y capacidades; `selectors.py`: consulta privada y contexto público mínimo; `schema_audit.py`: conciliación de solo lectura |
| `apps/websites/management/` | `__init__.py`, `commands/__init__.py`, `commands/audit_website_schema.py` |
| `apps/websites/migrations/` | `0007_website_editorial_revision_and_more.py` |
| `apps/websites/tests/` | `__init__.py`, `test_models.py`, `test_api.py`, `test_migrations.py` |
| `apps/api/v1/websites/` | `__init__.py`, `serializers.py`, `views.py`, `urls.py` |
| `apps/users/migrations/` | `0006_alter_permission_action_name.py` |
| Documentación | Este informe y `b1-regresion.json`; notas de estado en 05, 07 y 08 |

Archivos existentes modificados: `config/settings.py` (instalar app y política de dominios reservados), `.env.example` (dos opciones sin secretos), `apps/api/v1/urls.py` (include aditivo), `apps/users/models.py` (opción publish). No se modificaron vistas, serializers, selectores ni servicios existentes de autenticación, catálogo, inventario, ventas, POS o reportes.

## Modelos y decisiones técnicas

- **Website:** OneToOne Company, UUID, DRAFT por defecto, template ecommerce/schema de plantilla1. Se prepararon editorial_revision=0 y published_revision nullable sin implementar operaciones editoriales. Cambiar el nombre web no altera Company. No equivale a Store.
- **WebsiteDomain:** hostname IDNA/ASCII normalizado, unicidad global, rechazo de espacios/controles/IP/esquema/puerto/path/etiquetas inválidas; primario único por sitio. Restricciones SQL exigen hostname canónico, estados conocidos, evidencia temporal para VERIFIED/ACTIVE y primario ACTIVE. PENDING/VERIFYING/FAILED no acreditan verificación.
- **Esquema dependiente inactivo:** WebsiteSettings, WebsitePage, WebsiteSection, WebsitePageRevision, WebsiteMedia, WebsiteMenu, WebsiteMenuItem, WebsiteCatalogSettings y WebsiteProduct. No tienen endpoints ni señales de bootstrap/publicación en B1.
- **DNS:** no hay verificación productiva de control de dominio ni activación por API. Dominios ACTIVE en pruebas son fixtures explícitos y no una demostración de verificación DNS.
- **Plantillas:** ecommerce únicamente; se conservan template_key y versión para extensión posterior. Corporate sigue sin implementación ni habilitación.

### Autorización

`authorize_website_context` valida usuario activo, UUID de Company, membresía actual y contexto Store mediante las reglas ERP. Para Website se requiere además UserCompanyAccess vigente incluso si quedó un rol ADMIN antiguo; se conserva la excepción explícita de superusuario con Company activa. Esto es específico de Website, sin alterar autorizaciones heredadas.

Los permisos se obtienen de UserRole/RolePermission actuales y, cuando corresponde, del rol de sucursal vigente. No se confía en roles/permisos del JWT ni en el fallback ERP para módulos sin configuración. Lectura, edición, publicación, media y dominios permanecen separados. Revocar acceso o grants invalida la autorización aunque el token todavía esté firmado y no haya expirado.

### Selectores

- `get_company_website(user=..., company_id=..., store_id=..., website_id=..., permission=...)`: autoriza antes del queryset; consulta siempre por Company; UUID de otra empresa produce DoesNotExist. Company ausente falla sin consulta Website.
- `resolve_public_website(hostname)`: recibe un hostname explícito, no request/cabeceras. Requiere Company activa, Website PUBLISHED, fecha/referencia de publicación y dominio ACTIVE/verificado. La revisión debe ser del Home del mismo Website, con estado/versión publicados coherentes.
- La resolución devuelve `PublicWebsiteContext` con UUID, hostname, template y referencia de revisión; nunca snapshot, settings, datos fiscales, borrador o Company. Sin publicación configurada falla cerrado. B1 no proporciona una ruta HTTP pública.

## Único endpoint nuevo

`GET /api/v1/websites/current/`

Reutiliza JWTAuthentication mediante una subclase local que añade el desafío Bearer; no altera el autenticador existente. No acepta sesión como sustituto del ámbito JWT ni usa company_id de query, X-Company-ID o X-Forwarded-Host para autorización. GET no crea Website.

Response compatible con E0:

```json
{
  "id": "<uuid Website>",
  "companyId": "<uuid Company autorizada>",
  "templateKey": "ecommerce",
  "documentSchemaVersion": 3,
  "revision": 0,
  "capabilities": {
    "view": true,
    "edit": false,
    "publish": false,
    "mediaUpload": false,
    "domains": false,
    "realPublication": false
  }
}
```

documentSchemaVersion=3 comunica el contrato objetivo del editor, distinto del schema1 de plantilla; **no afirma que B1 ya pueda guardar documentos v3**. Capacidades edit/publish/mediaUpload/domains reflejan autorización actual; no implican endpoints disponibles en B1. realPublication permanece false. view se permite a quien tenga alguna capacidad editorial, según contrato05.

Respuestas: 401 sin JWT válido y `WWW-Authenticate: Bearer`; 403 sin empresa/membresía/capacidad; 404 si la empresa autorizada no tiene Website; 405 en escrituras. Errores `{code,message}`. Cache-Control `private, no-store` también en errores. No se implementó ETag editorial porque no hay escrituras B1.

Comparación de rutas con el commit base: **693 originales conservadas, ninguna retirada/cambiada, una ruta nueva**. No se registró el endpoint público de resolución ni rutas de guardar/publicar/media/catálogo.

## Pruebas ejecutadas

| Comprobación | Resultado |
|---|---|
| `manage.py check` | Correcto, cero incidencias |
| Grafo y consistencia de historial | Correctos en PostgreSQL aislado antes/después de recuperar fuentes |
| `makemigrations --check --dry-run` | Sin cambios pendientes |
| `migrate --plan`, aplicación en integración y `migrate --check` | Correctos; sin migraciones pendientes en esa instancia |
| `audit_website_schema` | Compatible antes (sin Website) y después (12 tablas) |
| 48 pruebas `apps.websites.tests` | Correctas en PostgreSQL tras el ajuste de nomenclatura; las 46 originales más dos pruebas de compatibilidad de historial |
| Preservación de datos | Probada en upgrades con Company, Store, Product/precios, Warehouse, StockByWarehouse, Customer, SalesQuotation y Movement previos |
| Divergencia | Tabla no registrada, historial desconocido, restricción ausente y dominio histórico incompatible detectados; sin reparación automática |
| Regresión completa B1 | 613 pruebas: 495 correctas, 83 fallos, 35 errores |
| Regresión commit base aislado | 567 pruebas: 449 correctas, mismos 83 fallos y 35 errores |
| Comparación de casos fallidos | Cero casos nuevos o resueltos; lista en JSON adjunto |
| URLs heredadas | 693 preservadas; única adición current Website |
| Frontend / Git | Sin cambios frontend, `.gitignore` previo preservado; sin cambios de rama/commit/push |

La regresión se repitió secuencialmente con los mismos ajustes **solo en memoria del runner** para base y B1: StaticFilesStorage para tests (sin generar manifiesto productivo) y MD5PasswordHasher para acelerar fixtures sintéticos. No se cambió el backend de almacenamiento ni el hasher de configuración de la aplicación. Se usó una clave JWT de test, no secretos productivos.

El intento inicial paralelo no completó la suite: faltaba soporte de serialización de tracebacks (tblib) y aparecieron fallos de manifiesto estático. No se instalaron dependencias para ocultarlo; la evidencia comparable es la ejecución secuencial completa posterior. Permanece un aviso de staticfiles no recolectado en el entorno de test.

Cobertura de matriz08: A01–A03, H01/H02/H04 y parte de H03 aplicable al endpoint privado; D01/D02 y R01 diferencial. E2E de proxy/Next/Host público pertenece a B3 y no se declara ejecutado. No se han probado DNS, R2, publicación o banner entre navegadores porque son fases posteriores.

## Riesgos y remediaciones priorizadas

| Prioridad | Hallazgo | Próximo tratamiento compatible |
|---|---|---|
| Alta, previa a activar web pública | Catálogos/inventory heredados pueden admitir contexto Company ausente y DTO con información interna | Entrega separada de remediación con tenant seguro por consumidor, contratos y pruebas; no mantenerlo como decisión permanente ni reemplazar por ?site= sin transición |
| Alta | Suite global heredada roja: 118 incidencias ya presentes en base | Corregir fixtures de acceso, rutas legacy inexistentes, expectativas y errores operativos por módulo; no atribuirlos a B1 ni declarar regresión global aprobada |
| Alta antes de migrar otra base | Historial/esquema de instalación habitual no conciliado en esta intervención | Auditar base autorizada y revisar plan; abortar ante divergencia sin --fake, borrado o renumeración |
| Operacional | DNS no verifica propiedad todavía | Servicio de verificación/control y activación autorizada antes de dominios reales |
| B2 | Esquema CMS recuperado aún no tiene snapshot v3 íntegro | Adaptador de documento, revisión global y publicación coherente de identidad/contacto/secciones |

La configuración local emitió advertencia de longitud de clave JWT en el primer ensayo; se usó una clave explícita de test en los ensayos posteriores. Revisar la configuración del entorno correspondiente antes de una futura activación, sin imprimir ni reemplazar secretos en esta entrega.

`audit_website_schema` es de solo lectura y compara estructura e historial local. No sustituye la revisión de operaciones/datos ni garantiza que una restricción manipulada con el mismo nombre conserve su semántica: para otra instalación revisar definiciones SQL y archivos históricos además del informe.

## Pendientes de B2 y límite de esta entrega

Guardar/cargar documento v3, mapping de bloques, snapshot completo, historial de guardados/restauraciones, control If-Match, servicios de publicación y media, preview autenticado y conexión del repositorio Next permanecen pendientes. No activar las rutas históricas de settings/páginas como atajo: eludirían el agregado/revisión diseñados.

Antes de integrar otra base: conciliarla y revisar la deuda de regresión. Antes de B3: definir dominios y contenido publicados reales. El primer banner visible desde otro navegador sigue siendo el hito B2+B3, **no un resultado de B1**.

Trabajo detenido en B1. La instancia PostgreSQL fue detenida y retirada junto con la copia temporal del baseline después de las verificaciones; el código, las migraciones y la evidencia resumida permanecen en el repositorio sin commit.

## Ajuste posterior: nombres descriptivos de migraciones y funciones

Se retiraron las etiquetas de etapa de desarrollo de los nombres activos de Website:

- `0003_website_pages_sections_and_revisions.py`: páginas, secciones, revisiones y permiso de publicación.
- `0004_website_theme_media_menus_and_seo.py`: tema, medios, menús y configuración SEO.
- `initialize_website_media_permissions_and_menus`: inicializa permisos y menús predeterminados.
- `remove_website_media_permission`: revierte el permiso de gestión de medios.

Se actualizaron la dependencia de 0004 a 0003, la dependencia de 0005 a 0004 y el grafo documental. Las operaciones de esquema/datos no cambiaron. `replaces` reconoce los nombres históricos para que Django no repita operaciones en una instalación ya migrada. `audit_website_schema` reconoce esos alias históricos y continúa rechazando migraciones desconocidas.

Pruebas añadidas: instalación con ambos nombres históricos registrados e instalación parcialmente migrada hasta 0003. Se verifican consistencia del historial, plan sin reaplicar lo existente, upgrade y auditoría física. Suite específica: **48 pruebas correctas sobre PostgreSQL 18.1**; check, grafo y makemigrations --check correctos. No se ejecutaron cambios sobre la base habitual.

El identificador `phase` de POS representa apertura/cierre de caja y no una etapa de desarrollo: se conserva su contrato de negocio. Los nombres de ramas históricas citados en B0 tampoco se modificaron. Las únicas referencias de etapa que permanecen en el código Website son los alias de compatibilidad dentro de `replaces`.
