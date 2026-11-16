# 08 — Matriz de pruebas y evidencia de aceptación

Estado B3: [integracion backend/Next y pruebas HTTP](11-entrega-b3.md) implementadas. R2 real y validacion visual en navegador siguen pendientes; no implica aceptacion integral ni habilita B4.

Fecha: 15/11/2026. Matriz de pruebas **a implementar/ejecutar** al desarrollar B1–B6. Su enumeración no significa que se hayan ejecutado ni que las pruebas históricas cubran el contrato nuevo.

Evidencia posterior B1: [48 pruebas específicas PostgreSQL, conciliación y regresión diferencial](09-b1-implementacion.md), incluidas dos pruebas de compatibilidad tras renombrar migraciones. Solo los escenarios B1 indicados en ese informe se consideran ejecutados; publicación y E2E del banner siguen pendientes.

Evidencia B2 posterior: [92 pruebas Website correctas en PostgreSQL y comparación completa con B1](10-entrega-b2.md). Los escenarios editoriales/medios allí enumerados ya fueron ejecutados; E2E del banner y consumo público por Next siguen pendientes para B3. R2 se probó con mocks controlados, no con el proveedor real.

## Datos y niveles

Dos empresas A/B activas, una inactiva, webs con estados DRAFT/PUBLISHED/SUSPENDED, dominios ACTIVE/verificados y PENDING/DISABLED/desconocidos. Usuario editor A, publicador A, lector A, usuario B, usuario revocado, administrador autorizado y superusuario según reglas ERP. Token genérico sin empresa, token scoped, expirado y contexto store ajeno/inactivo. Producto publicado/no publicado/inactivo/Company null de cada empresa; precios/listas, unidades y almacenes cruzados. Media A/B, archivo corrupto/activo/sobredimensionado.

- **U:** validación y adaptación puras, sin red real.
- **API:** DRF sobre BD aislada, contratos y permisos reales.
- **PG:** transacciones/migraciones sobre PostgreSQL, conexiones independientes para carreras.
- **E2E:** Next + Django + PostgreSQL y navegador; no mocks de persistencia/publicación.
- **Regresión:** suites ERP existentes y contratos de catálogos/login.

Mocks solo para R2/DNS/webhook donde corresponda, con pruebas separadas del adaptador real en entorno autorizado. No llamar R2/producción desde tests unitarios. SQLite rápido es útil para parte de la suite, pero no prueba select_for_update ni el comportamiento completo de constraints PostgreSQL.

## Casos

| ID | Caso / preparación | Resultado comprobable | Nivel / fase |
|---|---|---|---|
| A01 | Usuario A lee/editor/restaura/media/preview con UUID B | 404/denegación, ningún dato B ni escritura; consultas siempre acotadas | API, B1/B2 |
| A02 | Token sin empresa, expirado o membresía retirada; store ajeno/inactivo | 401/403 según contrato; cero consulta de catálogo global; permisos actuales, no claims antiguos | API, B1/B2 |
| A03 | Lector/editor/publicador y roles admin | Lector no edita, editor no publica, publicador no edita sin grant; no bypass si módulo no configurado; capacidades correctas | API+E2E, B1/B2 |
| H01 | Host normal/IDNA/mayúsculas/punto final; esquema, puerto, IP, path y controles | Normalización estable o 400; unicidad no permite doble dominio equivalente | U+API, B1 |
| H02 | Dominio desconocido/PENDING/DISABLED, Website DRAFT/SUSPENDED, Company inactiva | 404 uniforme; sin fallback ni identificadores internos ajenos | API+E2E, B1/B3 |
| H03 | Dos Hosts y cabeceras X-Forwarded-Host/X-Company-ID manipuladas | Next/proxy no adopta origen no confiable; API solo expone publicación del hostname registrado | E2E, B3 |
| H04 | Dominio duplicado/reservado, activación no autorizada, dos primarios | 400/403/409 y constraints; generar token no activa dominio; solo verificado puede ser primario | API+PG, B1 |
| P01 | Guardar nuevo banner/identidad/contacto sin publicar | E1 muestra draft nuevo; P1 mantiene snapshot anterior o404; revision pública no cambia | API+E2E, B2/B3 |
| P02 | Publicar contenido completo con permiso | Snapshot incluye identity/contact/SEO/hero/ocultos internos; pointer cambia atómicamente; público solo proyección visible | API+PG+E2E, B2/B3 |
| P03 | Error de validación/BD durante publicación | No pointer parcial, eventos falsos ni publicación mezclada; versión pública anterior intacta | PG+API, B2 |
| P04 | Historial paginado y restore de revisión válida/ajena | Orden/autor/fechas coherentes; restore crea nuevo draft y evento; published intacto; no se restauran referencias ajenas | API+E2E, B2 |
| P05 | Preview con/sin sesión y parámetros draft/source/embedded manipulados | Solo acceso autorizado, no-store/noindex; query pública no concede acceso; postMessage rechaza origen/ventana/empresa ajenos | API+E2E, B2 |
| C01 | Dos editores cargan ETag igual; A guarda/publica, B guarda/publica con el viejo | B recibe412; nunca sobrescribe; si falta ETag428; GET devuelve nueva revisión | API+PG+E2E, B2 |
| C02 | Escrituras concurrentes settings/banner/media-ref vía rutas antiguas y nuevas | Todas las escrituras documentales usan bloqueo/contador; no bypass por settings directo | PG+API, B2 |
| C03 | Guardado compite con publicación y hay webhook/cache opcional | Snapshot corresponde a una revisión completa; invalidación solo tras commit y tenant correcto; rollback no envía éxito | PG, B2/B6 |
| V01 | Documento v3: tipos, claves desconocidas, límites, enlaces, fechas, HTML/JS | 400 con fields exactos; sin ejecución ni pérdida silenciosa de campos | U+API, B2 |
| V02 | Roundtrip v1/v2/v3 y restore con banners ocultos/slider/contacto opcional | Conserva contenido; migration explícita de enlaces /catalog antiguos; links laborales v2 respetados; defaults compatibles | U+API, B2 |
| M01 | Upload/list/reference de imagen A y mediaId B | Solo media propia disponible; IDs/URLs ajenos rechazados; ownership backend, no URL cliente | API, B2 |
| M02 | PNG/JPEG/WebP válido vs SVG/HTML/MIME falso/data URL/corrupto | Formatos seguros procesados; demás400/415; draft sin éxito falso | U+API, B2 |
| M03 | Archivo >5MiB, dimensiones/píxeles excesivos, checksum duplicado concurrente y R2 fallando | 413/control de píxeles; dedup consistente; sin registros/archivos huérfanos permanentes ni secretos en errores | API+PG, B2 |
| M04 | Eliminar imagen referenciada por draft/revisión publicada/histórica | 409 o retención definida; snapshot sigue renderizando; soft-delete no rompe URLs publicadas | API+E2E, B2 |
| S01 | Inspección recursiva de respuestas públicas y payload RSC Next | Nunca costos/price_purchase/proveedor/margen/stock por almacén/draft/actor/tokens/Company ID; ocultos no filtrados al navegador | API+E2E, B3/B4/B5 |
| K01 | Producto/categoría/marca/lista/almacén de B o sin Company en sitio A | No aparece en lista/detalle/selección; vínculo inválido rechazado por API y servicio | API, B4 |
| K02 | Más de una página, OR multimarcas/multicategorías, búsqueda, rangos y facets | count global correcto, facetas de grupo acordadas, URLs preservadas; nunca filtra solo página local | API+E2E, B4 |
| K03 | Orden nombre/precio/discount, nulos/cero, empate y rango inválido | Orden estable, nulos al final, límites inclusivos; descuento solo con fuente; query inválida error documentado | U+API, B4 |
| K04 | Precio por vínculo/lista default/fallback, moneda, UOM, IGV y almacenes autorizados | Precio comercial coincide con resolvedor; sin doble impuesto; disponibilidad autorizada; no moneda/stock ajenos | API+PG, B4/B5 |
| Q01 | Carrito A incluye UUID B, inactivo, retirado y no publicado | REMOVED sin nombre/SKU/precio ajeno; no fuga por mensajes de error; total recalculado | API, B5 |
| Q02 | Cantidad 0/negativa/decimal/>999, >50 líneas, duplicados, unidad ajena y notas >240 | 400; no truncado silencioso ni conversión por factor cliente; ningún movimiento | U+API+E2E, B5 |
| Q03 | Cambio de precio/unidad/disponibilidad con quote anterior | Respuesta vigente; cambios visibles usando referencia verificable; primer quote no afirma detectar precio anterior | API+E2E, B5 |
| Q04 | Carrito persiste entre páginas, recarga y pestañas/empresas; storage corrupto | IDs de otras páginas se resuelven, sin mezclar tenants; corrupto informa estado; límite migrado explícitamente | E2E, B5 |
| Q05 | Quote expirado/manipulado, rate limit y WhatsApp | TTL/firma/tenant validados, 429; mensaje sin token/PII técnica; cero SalesDocument/SaleOrder/Movement/stock nuevo | API+E2E, B5 |
| D01 | Migrar desde PostgreSQL vacío y copia ERP con fuentes reconciliadas | Grafo aplicable, constraints/índices correctos, sin --fake; datos ERP preservados | PG, B1/B2 |
| D02 | Tablas/history websites divergentes, fuente faltante o snapshot viejo | Informe y bloqueo de aplicación automática; no borrar/reasignar; lector de revisión histórica probado | PG, B1/B2 |
| D03 | Backup/restauración y reversión de activación/publicación | Recuperación ensayada, sin pérdida de maestros ni contenido; no unapply destructivo como rollback de UI | PG+E2E, B6 |
| R01 | Suites ERP y contratos /catalog público/privado/inventory | Rutas/formas/permisos operativos preservados o adaptación explícita; seguridad sin nuevo fallback global | Regresión+API, cada fase |
| R02 | Login/select-company/refresh/logout y catálogos Next con sesión | Recupera ámbito/capacidades correctos; manejar 401/403; logout no se declara revocación real; precios catálogo correctos | API+E2E, B2/B4/B5 |
| R03 | Ficha inexistente, errores de red y media; móvil/teclado/reduced-motion | 404 HTTP real, sin200 de fallback streaming; carga/error accesibles; foco/Escape sin regresión; sin overflow | E2E, B3/B6 |
| E2E01 | Dos navegadores, dos empresas, banner guardado/publicado desde editor | Segundo navegador ve solo publicado de A desde PostgreSQL sin CMS localStorage; B no ve A; reinicio conserva contenido | E2E+PG, primer hito |

Pruebas complementarias de transporte: métodos no admitidos405; body demasiado grande413; CORS de origen permitido/ajeno, If-Match/ETag accesibles; CSRF válido/ausente si SessionAuthentication; timeout R2/API con error sin fallback; caracteres internacionales en textos/URLs; imágenes con alt; correos sin inyección. Probar grants de dominio/media por separado de publicación.

## Fixture contractual compartida

1. Extraer un documento v3 completo válido desde las reglas de `content.mjs`, sin datos demo de productos.
2. Validarlo con validateWebsite en Node y con serializer/adaptador Django; comparar rutas de errors y defaults opcionales.
3. Hacer roundtrip documento -> modelos CMS -> documento; conservar orden/IDs/enabled/contacto/CTA/slider.
4. Proyectar publicación y comprobar que no contiene contenido oculto. No aplicar el validador editorial íntegro a una respuesta pública recortada.
5. Mockear HTTP solo para tests de transporte; E2E01 usa endpoints y PostgreSQL reales.

## Comandos previstos, no ejecutados en esta auditoría

Después de preparar fuentes y entorno de integración, con configuración PostgreSQL verificada y aislada:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py test apps.websites.tests apps.inventory.tests.test_catalog_api
python manage.py test
```

Actualmente develop no tiene fuentes registradas websites: no presentar el comando de esa app como una comprobación ya disponible/completada. La suite global debe ejecutarse con la política de pruebas del repositorio; no apuntarla a BD productiva. Evitar confundir config/settings_test.py SQLite con el entorno PostgreSQL de D01/C01–C03.

Después de la futura conexión frontend:

```powershell
npm.cmd run lint
npm.cmd run build
node --test tests/commerce.test.mjs tests/website.test.mjs tests/admin-routes.test.mjs tests/storefront-api.test.mjs tests/contact.test.mjs tests/shop-filters.test.mjs
node tests/storefront-smoke.mjs http://localhost:3000
```

El smoke necesita servidor de pruebas iniciado. Añadir pruebas de integración para API real y navegador: las suites Node existentes validan lógica/demo, no prueban PostgreSQL/publicación. No instalar dependencias ni iniciar servidores productivos por esta documentación.

## Registro de evidencia de esta intervención

| Verificación | Estado real |
|---|---|
| Ramas/HEAD/estado local | Inspeccionados; backend develop, frontend mvp_website; .gitignore previo preservado |
| Fuentes históricas | Inspeccionadas con git show; sin recuperar/copiar código funcional al checkout |
| Frontend Node/lint | 40 pruebas correctas y lint correcto ejecutados en esta conversación antes de la documentación; no repetidos por cambios solo Markdown |
| Validación documental | Enlaces internos revisados; ejemplos JSON parseados; documento informativo de 05 validado con validateWebsite real del frontend y productIds vacío; sin cambiar su código |
| Django / PostgreSQL / migraciones | No ejecutados ni aplicados; compatibilidad BD pendiente |
| Flujo dos navegadores / dominios / R2 | Pendiente; criterio futuro E2E01 |
| Build/smoke/QA visual | No ejecutados en esta auditoría; referencias anteriores son históricas |
| Alcance de cambios | Solo ocho documentos nuevos de auditoría/diseño/plan; sin frontend/APIs/modelos/migraciones/configuración |

## Evidencia exigida al cerrar el primer hito

Registrar commits y ramas probados, motor BD sin secretos, pruebas A/P/H/C/M/D/R aplicables, revisión del banner y timestamps API, capturas del editor y navegador público de A/B, logs sin tokens y comprobación de ausencia de dependencia CMS localStorage. Incluir fallos conocidos y pruebas no ejecutadas. La disponibilidad del banner después de reiniciar el proceso y abrir un navegador limpio debe quedar demostrada, no inferida desde un build correcto.
