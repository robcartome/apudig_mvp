# B3-A y remediación P0 previa al catálogo

Actualización 17/11/2026: el usuario confirmó login/empresa obligatorios para `/catalog` y datos privados solo para superusuario o administrador de empresa. Se implementó la remediación de las seis lecturas de catálogo/productos y su adaptación Next; entrega y limitaciones en [17](17-remediacion-p0-catalogos.md). El resto conserva el diagnóstico **anterior** al parche, incluido `securityAccepted=false`; no describe el estado funcional posterior. B4-B continúa sin implementar.

Fecha: 16/11/2026. Baseline: informes [13](13-validacion-b3-a.md) y [14](14-auditoria-catalogo-b4-a.md). Backend `websites_backend@9e9eaf5`, frontend `mvp_website@83eb3ac`; se conservaron los archivos documentales no confirmados. Esta entrega prepara la remediación y los contratos; no cambia endpoints, permisos ni habilita comercio.

## B3-A: estado actualizado

La inspección actual, READ ONLY sobre PostgreSQL `apudig_mvp` localhost:5432, encontró `demo.localhost` **ACTIVE**, verified_at presente, is_primary=False y Website PUBLISHED. Esto actualiza el estado PENDING registrado en el informe13. El agente no realizó la atestación, activación ni ninguna actualización de registros.

Se comprobó además la existencia de eventos WEBSITE_DOMAIN_VERIFY y WEBSITE_DOMAIN_ACTIVATE para ese dominio, sin copiar su evidencia privada ni datos del actor al informe.

Configuración de archivo frontend confirmada, sin sobrescribirla: NEXT_PUBLIC_API_V1_URL y WEBSITE_API_V1_URL apuntan a `http://127.0.0.1:8000/api/v1`; WEBSITE_DEV_HOSTNAME es `demo.localhost`. NODE_ENV efectivo depende de cómo se inició Next; la respuesta por localhost demuestra el funcionamiento actual, no prueba por sí sola todas las variables heredadas del proceso.

La [evidencia HTTP actual](b3a-followup-http.json) demuestra:

- P1 para demo.localhost: 200, schema3 y commerceEnabled=false, private/no-store.
- localhost:3000: 200, identidad y título SEO del snapshot publicado presentes en HTML.
- Petición a Next con Host demo.localhost:3000: 200, la misma identidad/SEO publicados y no-store.
- Host desconocido: 404, sin fallback.
- `/management/websites/` sin sesión: 302 al login existente.

**B3-A sigue parcialmente aceptado.** Se cierra el bloqueo HTTP del dominio pendiente, pero no hay prueba visual autenticada, responsive, teclado, conflicto entre dos editores en navegador ni R2/CDN real. La herramienta volvió a devolver `The browser access host is unavailable`. No se simula esa aceptación con HTML o tests unitarios. El backend inspeccionado carece de bucket/credenciales R2; se comprueba su presencia como booleanos, sin imprimir secretos. Esto describe la configuración cargada por la auditoría, no una introspección del entorno privado del proceso servidor.

No se repitió la suite133 del baseline sin cambios funcionales nuevos. El informe13 conserva sus133 pruebas PostgreSQL y45 Node como evidencia de aquella ejecución; esta entrega añade HTTP actual y diagnóstico aislado del legado. No se declara la suite ERP global aprobada.

### Procedimiento exacto del operador

1. Iniciar sesión en `http://localhost:8000/`, seleccionar la empresa y abrir `http://localhost:8000/management/websites/`. Comprobar que se está operando su Website existente, sin crear otro.
2. Si el dominio está PENDING o DISABLED: personal APUDIG con is_superuser abre **Registrar comprobación de control (APUDIG)**, realiza la comprobación fuera del formulario y describe su evidencia real (20–1000 caracteres, sin secretos). Para localhost, documentar el aprovisionamiento local autorizado. Pulsar **Registrar verificación manual**. No representa una consulta DNS automática.
3. En VERIFIED, pulsar **Activar dominio verificado**. En ACTIVE, pulsar **Usar como principal** solo si se ha decidido que sea el canonical principal. Hoy el dominio ya está activo: no volver a atestiguarlo ni desactivarlo para repetir esta guía. La elección de principal no es requisito del200 observado; el resolver usa el hostname activo cuando no hay principal.
4. Abrir localhost:3000 y demo.localhost:3000. Para futuras modificaciones de variables, reiniciar Next con `npm.cmd run dev`; el override no funciona con next start en producción.
5. Probar login, empresa, editor, guardado y publicación desde la UI real; guardar un cambio nuevo no debe modificar la publicación anterior. Publicar explícitamente y revisar desde un navegador limpio. Para dos empresas usar datos autorizados; no sembrarlos en la base habitual automáticamente.
6. Configurar un entorno R2 de integración autorizado por el operador y validar un upload nuevo, preview, publicación, lectura CDN y retención. No escribir en bucket productivo ni mover claves históricas para completar esta lista.

## Consumidores actuales del catálogo heredado

| Endpoint / servicio | Consumidor observado | Dependencias que deben conservarse |
|---|---|---|
| GET `/api/v1/catalog/products/` → getCatalogProducts | `/catalog`, CatalogPage con isAdmin=false | total/limit/offset/results, búsqueda y scroll; tarjetas nombre/SKU/unidad/marca/categoría/precio/imagen |
| GET `/api/v1/catalog/products/{id}/detail/` → getProductDetail | ProductDetailModal público/laboral | Modal compartido; hoy puede mostrar price_list y stock_by_warehouse sin autorización especial |
| GET `/api/v1/catalog/private/products/` → getCatalogProductsPrivate | `/admin/catalog_admin`, CatalogPage isAdmin=true | Mismo envelope; tarjeta administrativa usa price_purchase |
| GET `/api/v1/catalog/private/products/{id}/detail/` → getPrivateProductDetail | ProductDetailModal isAdmin=true | Precio de compra y secciones de precios/almacenes internas |
| getProducts → `/api/v1/products/` | Componentes históricos de búsqueda, movimientos y cotizaciones Next | Otro endpoint, no alias del catálogo; esas páginas ERP están en transición a Django |
| Servicios storefrontProducts/Categories | Preparados pero no conectados al catálogo real | Usan `/stores/{storeId}` y store_id; no consumirlos a ciegas con K0–K3 |

`productsService.js` usa apiFetch: adjunta JWT si existe, pero admite ausencia de token. Por eso mantener una URL o el envelope no basta para autorizar una consulta. CatalogPage no maneja adecuadamente todos los errores de carga ni reinicia sus datos por Company explícitamente. La búsqueda usa ERP; filtros por categoría/marca se aplican localmente a lo ya cargado.

ProductDetailModal mantiene un objeto de caché de módulo indexado solo por productId; no separa empresa, usuario, modo público/privado ni permisos. Puede reutilizar datos de un contexto anterior sin consultar el servidor. La remediación debe eliminar esa caché o segregarse por contexto y vaciarse en cambio de empresa/sesión/permisos. El servidor no puede revocar datos ya guardados en memoria del cliente por sí solo.

El rastreo en los dos repositorios no identificó otros consumidores activos de esos cuatro endpoints. Existen tests históricos que solicitan `/catalog/products` fuera de `/api/v1/`; no se debe asumir que son alias vigentes ni copiarlos como especificación. Antes de un corte productivo, inventariar integraciones externas mediante operación autorizada; ausencia en el repo no prueba ausencia en producción.

## Diagnóstico reproducible P0

Se añadió [catalog_security_probe.py](catalog_security_probe.py), herramienta de diagnóstico explícita, no un test de aceptación del catálogo seguro. Se ejecuta desde backend con:

```powershell
.\.venv\Scripts\python.exe docs\architecture\website-integration\catalog_security_probe.py --run-isolated
```

Fuerza una base de prueba separada `test_apudig_catalog_security_audit`, solo PostgreSQL local; crea A/B, productos, precio y almacén sintéticos y los elimina al terminar el runner. No consulta productos reales ni usa R2. La ejecución correcta del diagnóstico no significa que la seguridad pase: el [resultado](catalog-security-probe.json) contiene securityAccepted=false.

Hallazgos reproducidos en PostgreSQL:

| Comprobación | Estado actual inseguro observado | Resultado exigido tras remediar |
|---|---|---|
| Listado anónimo sin empresa | Devuelve productos de A y B | Denegación antes de consulta de productos |
| Detalle anónimo | Devuelve lista de precios interna | No ofrecer ese campo en proyección pública |
| Detalle anónimo | Devuelve ubicación/stock por almacén | No ofrecer detalles de almacén públicamente |
| JWT de A con membresía revocada | Sigue leyendo costos de A | 403 y sin datos |
| Empresa inactiva con JWT aún válido | Sigue siendo legible | 403 y sin datos |

La exposición de supplier_codes está además confirmada en los serializers y en el prefetch; su búsqueda usa códigos/nombres de proveedor. El diagnóstico no volcó datos ni códigos reales. Los cinco casos observados son brechas actuales, no fallos introducidos por documentación.

### Bypass adyacente que no debe quedar sin seguimiento

ProductListAPIView y ProductDetailAPIView de `apps/api/v1/inventory/views.py` también son AllowAny y llaman a get_products con contexto opcional. Proteger solo las cuatro rutas catalog dejaría otra vía de lectura ERP. Incluir sus rutas reales `/api/v1/products/` y detalle en el análisis y la remediación de acceso, con sus consumidores internos y serializers, sin modificar el maestro ni reglas de inventario. Las demás APIs que usan contexto opcional requieren revisión independiente antes de exposición externa.

## Remediación propuesta compatible

**Recomendación:** tratar las cuatro rutas heredadas como catálogo laboral autenticado, manteniendo sus URLs y el envelope total/limit/offset/results. El catálogo verdaderamente público del Website irá en K0–K3 por hostname verificado. Esto cambia deliberadamente la antigua lectura anónima: compatibilidad de seguridad no significa conservar consultas globales. La decisión de exigir login en `/catalog` debe aprobarse y comunicarse antes del cambio funcional.

Si se necesita compartir un catálogo sin login, la alternativa segura es una proyección anónima por hostname sobre productos/lista/almacenes expresamente autorizados; requiere un contrato de publicación y puede planificarse con K0–K3. No mantener un modo anónimo global como puente mientras se decide.

### Backend del parche P0, previo a B4-B

1. Aislar un resolvedor obligatorio del contexto privado para catálogo/inventario: JWT válido de usuario activo; company_id firmado obligatorio; validar Company activa, membresía actual y sucursal si existe. No aceptar company_id de query/body ni recurrir a una empresa de sesión si falta la claim. Un superusuario también debe seleccionar empresa explícita para estas rutas; su excepción ERP no autoriza una consulta global accidental.
2. Si falta token,401 con challenge Bearer; token genérico sin empresa,403 COMPANY_REQUIRED; membresía revocada/Company inactiva/sucursal ajena,403. UUID ajeno de recurso,404 uniforme. Malformado de contexto, denegación antes de consultar productos.
3. company_required=True por sí solo **no corrige** BaseCompanyAPIView: hoy retorna None si falta contexto. El resolvedor debe lanzar una excepción antes de llamar a los selectores. No cambiar globalmente get_products/filter_by_company sin revisar los usos ERP autorizados; crear un wrapper estricto de catálogo que nunca invoque esos helpers con None.
4. Revalidar permisos de lectura ERP realmente configurados, no solo IsAuthenticated o claims antiguas. Para información sensible exigir además una capacidad explícita de costos/listas/almacenes/proveedores o administración de la Company. El fallback legado de user_has_company_permission cuando falta un módulo no debe conceder nuevos permisos sensibles. Elegir/provisionar esos permisos es una decisión previa, no un grant automático de esta entrega.
5. Separar serializers laborales básicos de privados. Básico sin costos/proveedores/listas internas/ubicaciones. Privado incluye solo campos autorizados por operación; si faltan permisos,403 o proyección documentada sin esos campos, nunca ampliar porque el cliente envía isAdmin=true. La política exacta por rol requiere aprobación; no retirar silenciosamente datos de un usuario que sí está autorizado.
6. Acotar producto y todas las relaciones secundarias por la Company: precios, categorías/marcas y stock de almacenes de Store activa/autorizada. El prefijo de imagen o un UUID no reemplaza ownership.
7. Respuestas privadas no-store; no mezclar cachés entre usuarios/empresas. Mantener paginación20/máx100 y parámetros actuales; no introducir filtros de publicación Website en el catálogo laboral autenticado, porque su propósito es consultar ERP, no solo productos comerciales publicados.

### Frontend del parche P0

- Conservar `/catalog` y `/admin/catalog_admin`. En la opción recomendada, `/catalog` pide la misma sesión/selección de empresa existente; no se incorpora otro login.
- El cliente mantiene getCatalogProducts/Private y las rutas actuales, pero conserva status/code/fields para401/403. Mostrar reingreso/selección de empresa o acceso denegado; siempre liberar loading y evitar mostrar la respuesta anterior ante errores.
- CatalogPage debe remontarse o reiniciar datos/paginación/filtros al cambiar Company/modo/sesión, y cancelar/ignorar respuestas antiguas. Su callback debe depender del contexto real, no solo página/búsqueda.
- Eliminar o separar la caché de ProductDetailModal por Company/usuario/modo; vaciar datos al cerrar o cambiar contexto. No mostrar primero datos de la caché privada mientras se solicita una proyección básica.
- Tarjetas/modales muestran secciones privadas solo cuando el backend las autoriza; campos ausentes no se convierten en costos0.00. Mantener nombres de campos autorizados para consumidores existentes y registrar cualquier deprecación.
- Probar login/refresh/selección de empresa, scroll, búsquedas, filtros existentes y ambos modales antes de desplegar el parche.

## Decisiones pendientes antes del parche

1. Confirmar si `/catalog` laboral puede exigir login. Si debe seguir anónimo, aprobar su contrato público por dominio y la fuente de productos/precios permitidos; no puede seguir global.
2. Aprobar qué roles acceden a compra, todas las listas, almacenes y códigos de proveedor; reutilizar permisos existentes equivalentes si los hay o provisionar capacidades explícitas, sin alterar modelos.
3. Inventariar clientes externos y acordar un corte coordinado backend/frontend. Una ventana de compatibilidad no debe mantener exposición global activa.
4. Aprobar el alcance de la corrección adyacente `/products/` para que no sea un bypass del catálogo protegido. No hay cambio de reglas operativas de inventario en esa propuesta.

No se implementó el parche P0 en esta entrega: las brechas permanecen identificadas y reproducibles. No se iniciará B4-B ni se declarará seguro el catálogo hasta resolver estas decisiones y ejecutar su matriz de aceptación. Los contratos y reglas comerciales están en [16](16-contratos-y-politica-b4-b.md).
