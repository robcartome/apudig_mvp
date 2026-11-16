# 06 — Seguridad y aislamiento multiempresa

Fecha: 15/11/2026. Análisis estático y requisitos para implementación; no se ejecutaron pruebas de intrusión ni consultas de datos ajenos.

## Fronteras de confianza

| Entrada | Confiar para | No confiar para |
|---|---|---|
| JWT firmado y vigente | Identidad y contexto candidato de empresa/sucursal | Membresía o permisos actuales sin consulta; acciones editoriales por claims cliente |
| UserCompanyAccess / roles en BD | Validar acceso actual mediante reglas ERP | Autorizar empresa ajena por un ID recibido |
| Host público | Seleccionar hostname tras normalización/proxy | Conceder permiso editorial o generar company_id global |
| WebsiteDomain en BD | Resolver contenido público si ACTIVE/verificado | Considerar verificado un hostname solo porque existe registro |
| Documento v3 | Datos de texto/estructura tras validación | Ejecutar HTML, JS, CSS o URLs arbitrarias como código |
| Precios/cantidades del navegador | Solicitud de cantidad dentro de límites | Precio, costo, conversión, empresa o reserva de stock |
| URLs y archivos | Mostrar recursos del canal permitido | Probar ownership, leer rutas locales o hacer fetch arbitrario servidor |

## Hallazgos del estado actual y respuesta prevista

| Evidencia | Riesgo | Tratamiento |
|---|---|---|
| develop `BaseCompanyAPIView.get_company_id`, `filter_by_company` y `inventory/selectors.py:get_products` admiten None | Consulta global si falta empresa | Nueva API requiere tenant explícito antes del queryset; no alterar helper global sin auditar todos sus consumidores |
| catalog público AllowAny/company_required=False; DTO con supplier_codes y stock_by_warehouse | Mezcla de empresas e información interna | Endpoint nuevo dedicado, lista permitida de campos y aislamiento obligatorio; remediar legado con pruebas de compatibilidad |
| inventory ProductList/Detail AllowAny | Recursos administrativos accesibles sin autenticación requerida por el futuro CMS | Revisión de exposición prioritaria; endurecimiento planificado con contratos de consumidores, no usar como API pública web |
| IsCompanyUser develop solo exige contexto | Token/contexto no garantizan membresía vigente | Reutilizar user_can_access_context y verificación empresa/store activo; aplicar a cada operación |
| user_has_company_permission permite módulo no configurado | Acceso involuntario antes de sembrar permisos | Regla website explícita que deniega si no existe concesión; nunca depender del fallback legado |
| website_v0 settings públicos fuera del snapshot | Cambios de borrador visibles sin publicar | Toda lectura informativa desde referencia a snapshot completo |
| JWT refresh y logout stateless | Revocación inmediata no garantizada; claims no siempre conservan permisos al renovar | Revalidar permisos de servidor; probar refresh/selección; documentar deuda sin crear otro login |
| Preview histórico firmado por página | Token en URL/log/cache y vida de borrador | Primera entrega preview autenticado, no-store/noindex; token remoto posterior de alcance limitado |
| Media histórico soft-delete solo controla logo/favicon en delete | Puede retirar medios usados por otras revisiones/bloques | Referencias explícitas y retención de snapshots; no borrar recurso referenciado |

No atribuir una explotación HTTP a estos hallazgos: se derivan del código. La remediación del legado no puede consistir en mantener una fuga por preservar compatibilidad; definir tenant seguro para cada consumidor y estados de denegación antes de activación. Crear API nueva por sí sola no arregla exposición antigua.

## Autorización privada por operación

1. Autenticar con el sistema existente. Validar usuario activo y JWT tipo access.
2. Obtener Company del contexto autenticado; si hay store, validar que pertenece a Company y está activo.
3. Revalidar acceso actual con reglas de `apps/users/permissions.py:user_can_access_context` y grants reales. Un company_id firmado antiguo no mantiene membresía retirada.
4. Consultar Website por PK **y** company_id; un UUID impredecible no sustituye filtrado.
5. Evaluar acción read/manage/publish/media/domains, respetando superusuario/administrador autorizado del ERP y separación editor/publicador.
6. Validar relaciones secundarias: media.website_id, product.company_id, category/brand.company_id, price_list.company_id, warehouse.store.company_id.
7. Bloquear agregado y comprobar ETag para escribir; volver a validar referencias al publicar.

No usar `websites.change_website` como permiso de servidor sin mapearlo: es un codename frontend propuesto. API retorna capacidades y Next adapta sus controles; ocultar un botón solo mejora UX.

## Dominio, proxies y suplantación de Host

- Normalización: lower, quitar punto final, IDNA a ASCII; validar etiquetas/longitud, rechazar esquema, credenciales, puerto, ruta, controles, comodines arbitrarios e IP. Reutilizar normalize_hostname histórico y probar casos adversos adicionales.
- Los hostnames son únicos globalmente; el primario único por web. Registro PENDING no publica nada. ACTIVE exige evidencia de control y activación autorizada. `verified_at` escrito manualmente en datos de prueba no prueba un flujo DNS productivo.
- Next obtiene dominio público del Host aceptado por el borde. El proxy debe validar el dominio y sobrescribir cabeceras forwarded; no elegir el primer X-Forwarded-Host de origen externo. Sin proxy confiable, no usar forwarded para resolver tenant.
- Django valida su propio ALLOWED_HOSTS para la API y resuelve el hostname solicitado contra registro. No equiparar Host de api.apudig.com con dominio de empresa ni aceptar un X-Company-ID público.
- Consultar un hostname público en una ruta/query no requiere secreto: se exponen solo publicaciones. Un cliente puede elegir qué sitio público leer, pero eso nunca le concede editor/preview.
- Host desconocido, dominio DISABLED, Website SUSPENDED, empresa inactiva o sin publicación: 404 uniforme sin fallback a primera web/demo. Malformado: 400 sin detalles de infraestructura.
- Canonical y enlaces absolutos provienen del dominio primario activo registrado, nunca de cabeceras sin verificar. No construir redirects a URL arbitraria.
- Subdominios de plataforma se asignan desde un registro autorizado, excluyendo apex/labels reservadas. Dominios personalizados exigen verificación DNS/control real y unicidad; futura expiración/reverificación se documentará operacionalmente.
- En integración local se pueden provisionar dominios de prueba mediante fixtures/entorno autorizado; no cambiar DNS ni configurar dominios productivos durante esta auditoría.

## Caché y publicación

Primera versión no-store tanto en fetch SSR como en respuesta pública. La ruta Next debe renderizar según request: no prerenderizar un sitio fijo y servirlo a todos los Hosts. No combinar bootstrap de un tenant con contenido de otro.

Al habilitar caché después: clave incluye Website UUID, idioma, revisión publicada, proyección y query normalizada de filtros. Separar público/editor/preview; caché en edge debe incluir Host. Guardar draft no invalida contenido público porque no lo modifica. Publicar confirma transacción antes de invalidar; webhook autenticado, origen controlado, payload acotado y reintentos/TTL. No usar un endpoint de invalidación arbitrario enviado por el editor. Suspender dominio/empresa invalida caché de inmediato o exige comprobación de estado que impida servir contenido desactivado.

## Contenido, media y transporte

- Texto plano y campos permitidos, límites por campo, colección y body; no dangerouslySetInnerHTML ni JSON de bloques no registrados. Rechazar claves desconocidas que puedan convertirse en atributos ejecutables.
- Enlaces internos según isSafeLink; no `//`, backslash, controles o javascript. Redes solo HTTPS/hosts autorizados por red, sin credenciales. No transformar correo/teléfono en headers o parámetros libres.
- Archivo validado por contenido Pillow, tipo permitido, tamaño/píxeles/dimensiones, nombre generado y procesamiento controlado. Rechazar SVG/HTML y bombas de descompresión. No confiar en extensión ni MIME del navegador.
- Archivos segregados por Website y ownership en BD; DTO público no expone storage_key privado. No fetch de URL arbitraria para importar imágenes (SSRF). URLs externas deben deshabilitarse en modo real o pasar por política explícita de recursos autorizados.
- R2 y PostgreSQL no forman una transacción única: prever limpieza de uploads huérfanos y no reportar guardado si falla el registro. Nunca borrar un archivo todavía referenciado por snapshot retenido.
- CSRF: llamadas Bearer sin cookies mantienen autenticación existente. Si se acepta SessionAuthentication, conservar CSRF en métodos inseguros; no desactivarlo para resolver errores frontend. Preview autenticado aplica la misma regla.
- CORS: orígenes concretos del editor, credentials según autenticación elegida, permitir If-Match/exponer ETag; CORS no es control de tenant ni reemplaza permisos.
- Tokens no viajan en URL/postMessage público/logs. Preview en iframe valida origen, ventana, empresa; sesión/backend siguen siendo autoridad. Token preview remoto opcional: firmado, corto, ligado a Website/revisión, no-cache/noindex, sin token administrativo.
- Rate limits públicos y editor por operación, límites de payload, timeouts de almacenamiento; validar IP desde proxy confiable. Rate limit por proceso no basta en despliegue multiinstancia.

## Concurrencia y datos comerciales

Todos los escritores editoriales adquieren bloqueo Website, comprueban editorial_revision y registran nueva revisión/evento en atomic. Un lector no debe ver pointer nuevo antes del snapshot; invalidación ocurre on_commit. Inmutabilidad debe cubrir servicios y accesos administrativos: override save no impide QuerySet.update/delete. Prohibir esas rutas sobre revisiones y protegerlas con permisos/servicios/tests; evaluar restricciones adicionales de BD si se requiere garantía frente a escritores externos.

Carrito B5 acepta producto y unidad solo del sitio publicado y recalcula precio/total. IDs ajenos/retirados regresan REMOVED sin nombre/SKU/precio. UNKNOWN no implica stock garantizado; reglas de can_submit reflejan solicitud, no pedido. No tocar stock ni caja ni serie fiscal al abrir WhatsApp. No incluir notas/teléfono/PII en analítica técnica.

## Condiciones de salida

La matriz [08](08-matriz-pruebas.md) prueba dos empresas, membresía retirada, UUID cruzado, contenido oculto, proxy y caché, media ajena y carreras reales PostgreSQL. Ninguna etapa se declara segura solo por mostrar controles correctos en Next o pasar tests sobre SQLite.
