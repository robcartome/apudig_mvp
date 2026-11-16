# 04 — Modelo de datos y estrategia de migraciones

Fecha: 15/11/2026. Diseño sin crear/aplicar migraciones, sin consultar BD y sin usar --fake.

## Reutilización y ampliaciones

| Entidad | Base recuperable | Ampliación propuesta / integridad |
|---|---|---|
| Company/Store/UserCompanyAccess | develop | Sin modelos paralelos; autorización actual revalidada por operación |
| Website | websites_v0 | Conservar OneToOne Company; editorial_revision >= 0, published_revision nullable PROTECT, referencia solo a Home de la misma web; template registrada |
| WebsiteDomain | websites_v0 | hostname normalizado único global; como máximo un primario por web; ACTIVE exige verificación; administrado separadamente del documento |
| WebsiteSettings | websites_v0 | Incorporar short_name/location/announcement/secondary_phone y representación explícita hours texto; ampliar redes con X; bounds v3. Es borrador, no lectura pública directa |
| WebsitePage | websites_v0 | Conservar un Home por web; SEO v3 180 frente a 170 histórico mediante cambio incremental; páginas estándar futuras sin nuevo CMS |
| WebsiteSection | websites_v0 | Tipos ampliados y configuraciones estrictas; conservar ID editorial, orden y enabled; singleton según tipo; validación de documento total |
| WebsitePageRevision | websites_v0 | Snapshot inmutable completo; operation SAVE/PUBLISH/RESTORE/BASELINE, referencia de origen al restaurar y editorial_revision asociada; secuencia version única por página |
| WebsiteMedia | websites_v0 | Ownership, archivo/hash/MIME/tamaño/dimensiones, retención de medios referenciados por revisiones; no hard delete publicado |
| WebsiteAuditEvent | Nuevo, si la revisión no cubre el evento | Auditoría append-only de operación, actor, web, revisión y fecha; acceso/errores a logs sin datos sensibles; no almacena documento paralelo |
| WebsiteMenu/MenuItem | websites_v0 | Conservar para futuro; no activar escritura que eluda la revisión global; snapshots del agregado si se publican |
| WebsiteProduct/CatalogSettings | websites_v0, B4 | Mantener vínculos explícitos al ERP, no crear Product público maestro |

No se necesita otro WebsiteRevision ni WebsitePublication: ampliar WebsitePageRevision y utilizar una referencia a revisión publicada. La relación de published_revision con el Home requiere validación de servicio y pruebas: una FK simple no prueba igualdad de tenant. El mismo requisito aplica a relaciones de media y productos.

`original_price` y descuento no existen como política comercial recuperada: no inventar precios anteriores para satisfacer tarjetas. Se devolverán null hasta definir una fuente autorizada. Categorías destacadas por ID solo se añadirán a un esquema posterior si se solicita su edición; no cambiar v3 silenciosamente.

## Grafo conciliado con nombres descriptivos

Las migraciones 0003 y 0004 usan nombres de su responsabilidad. Sus nombres históricos se reconocen mediante `replaces` para conservar compatibilidad con instalaciones existentes; no se deben borrar registros ni usar --fake para adaptarlas. Ver el ajuste de nomenclatura en [09](09-b1-implementacion.md).

```text
companies.0015_companybranding_show_company_name_with_logo
  -> websites.0001_initial
users.0005_useroperationalflags_can_correct_pos_payment + AUTH_USER_MODEL
  -> websites.0002_website_foundations (también depende de 0001)
users.0005 + AUTH_USER_MODEL + websites.0002
  -> websites.0003_website_pages_sections_and_revisions
AUTH_USER_MODEL + websites.0003
  -> websites.0004_website_theme_media_menus_and_seo
inventory.0022_product_company_barcode_index + websites.0004
  -> websites.0005_websitecatalogsettings_websiteproduct
websites.0005
  -> websites.0006_website_template
```

Los archivos de dependencias companies/users/inventory indicados existen en develop. No se identifica por esta comparación una colisión de nombres con migraciones fuente websites en develop, porque no las hay; esto no acredita ausencia de conflicto con la base real ni sustituye MigrationLoader/plan en entorno reconciliado.

0002 siembra permisos read/manage/domains y defaults; 0003 siembra publish.website y Home; 0005 crea configuración y publicaciones vacías, sin publicar productos; 0006 depende de 0005 aunque la primera entrega sea informativa. Recuperar cadena consistente no obliga a activar las APIs comerciales.

El histórico usa action_name publish en un permiso, pero Permission.ACTION_CHOICES de develop no contiene publish. Una migración RunPython puede haberlo insertado sin validación de choices. Antes de incorporarla, definir compatibilidad: preservar código publish.website y ampliar choice/etiqueta de forma aditiva si es necesario, sin renombrar permisos operativos ajenos ni reescribir migraciones ya aplicadas.

## Procedimiento previo obligatorio

1. Inventariar fuentes Git históricas y su hash; conservar copia verificable de 0001–0006. No reconstruir esquema desde .pyc.
2. En un entorno autorizado posterior, obtener solo inventario de tablas/constraints/índices y `django_migrations` de websites y dependencias; no exportar datos comerciales a docs.
3. Comparar el esquema físico con el estado de migraciones y los archivos recuperados; identificar si el código histórico se aplicó alguna vez.
4. Verificar versión/motor de BD efectiva sin imprimir credenciales. Ensayar sobre copia PostgreSQL o BD de integración, nunca improvisar en producción.
5. Resolver el escenario aplicable antes de crear migraciones nuevas.

| Escenario de BD | Estrategia |
|---|---|
| Sin tablas ni historial websites | Recuperar cadena compatible 0001–0006; ensayar desde BD vacía y desde copia ERP existente; después migraciones incrementales de integración |
| Tablas y migraciones históricas coinciden | Restaurar exactamente fuentes aplicadas, no modificar historial; añadir extensiones incrementales |
| Historial o esquema divergentes / tablas sin historial | Detener migración funcional; informe de diferencias y plan explícito de conciliación/recuperación. No --fake ni borrar tablas como atajo |
| Nodos faltantes o permisos históricos inconsistentes | Recuperar fuentes originales/confirmar dependencias y diseñar reparación incremental comprobada; no renumerar archivos aplicados |

## Migraciones de ampliación, nombres todavía no asignados

1. **Expandir:** campos nullable/default seguro, metadata de revisión, auditoría y límites v3; no cambiar FKs fiscales ni maestros ERP. Mantener lectores de snapshots viejos.
2. **Conciliar:** generar baseline a partir de datos existentes mediante adaptador validado. Guardar todo lo necesario para reconstruir el borrador. No publicar automáticamente una web ni asociar una empresa por nombre.
3. **Publicación:** solo establecer referencia publicada desde una revisión histórica realmente publicada y compatible; si falta configuración publicada verificable, mantener web no pública y pedir revisión editorial, sin promover el borrador actual.
4. **Constraints:** aplicar unicidad/relaciones requeridas tras auditar datos; filas huérfanas o cross-tenant se reportan, no reasignan silenciosamente.
5. **Cambiar consumidores:** nueva API lee pointer/snapshot; escrituras pasan por contador/bloqueo global. Publicación de productos continúa apagada hasta B4.

No duplicar draft JSON y Settings/Sections como autoridades simultáneas. Las revisiones guardan copias históricas inmutables y no se editan al cambiar el modelo actual. Los campos nuevos de contacto opcionales y heroSlider ausente deben aceptar defaults compatibles.

## Datos locales frontend

No migrar localStorage mediante una migración Django. Cuando se habilite API, importación opcional y explícita de un borrador de la misma empresa: validar documento, reemplazar imágenes inline por media, eliminar/rechazar IDs demo y guardar como nueva revisión. Nunca importar/publish automático ni borrar datos locales del usuario al cambiar de modo.

Primera aceptación usa un documento nuevo con banner y secciones informativas, especiales vacíos y campañas sin referencias de productos. El catálogo no bloquea este hito.

## Ensayo, reversión y criterios

- Preparar backup/restauración comprobados antes de ejecutar cambios reales.
- Revisar `migrate --plan`, `sqlmigrate` para cada migración nueva y `makemigrations --check --dry-run` en el código preparado; comandos aquí son futuros, no ejecutados.
- Ejecutar migraciones sobre PostgreSQL vacío y sobre copia ERP; comprobar conteos, FKs y valores de Company/Product/precios/stock/ventas antes y después.
- Probar upgrades de snapshots v1/v2 a v3 y lectura de revisiones históricas sin pérdida de ocultos.
- Revertir activación por flag/ruta a última revisión pública válida; no usar un unapply destructivo para deshacer un fallo visual.
- Migraciones reversibles solo tras conservar contenido nuevo y ensayar compatibilidad. Quitar 0005 destruye vínculos y textos web aunque no elimine Product; no es rollback rutinario.
- Publicación rota se corrige restaurando una revisión al draft y publicándola, conservando historial; un endpoint de mantenimiento puede suspender la web sin exponer borrador.

Aceptación de B1/B2: grafo conciliado con BD real, ensayos PostgreSQL correctos, maestros ERP intactos, rollback documentado y ninguna publicación implícita.
