# B4-C4 — Validación y aceptación de Website y catálogo

18/11/2026, America/Lima. **Aceptación técnica acotada; piloto todavía condicionado a configuración comercial real, QA visual completa y R2/CDN real.** No se activa comercio ni se inicia B4-D.

## Entorno y alcance

Backend `websites_backend@e3f479f`, frontend `mvp_website@856b711`; se preservan los diffs sin confirmar de B4-B, B4-C y del ajuste laboral posterior. Se leyeron AGENTS de ambos repositorios, informes20/21/22 y continuidad frontend. No checkout/merge/commit/push/despliegue, dependencias nuevas, modelos o migraciones. El backend no está en develop: es la rama real de trabajo ya documentada; no se cambió.

PostgreSQL local18.1, Django5.2.19, DRF3.18.3, Next16.0.10 y React19.1.0. Django8000 y Next3000 responden. Auditoría de `apudig_mvp` dentro de transacción **READ ONLY**: historial consistente y ninguna migración pendiente. `demo.localhost` ACTIVE/verificado, Website PUBLISHED, empresa activa y revisión17. Sin modificaciones de ese estado.

El Website habitual tiene **0 vínculos de producto, ninguna configuración comercial, lista predeterminada ni almacenes autorizados**. `/shop` vacío es correcto; el detalle de un producto publicado habitual no se puede aceptar hasta que su administrador lo configure. No se crea una empresa/Website/producto ni política como fallback. En la página se observan títulos editoriales aún genéricos/en inglés y datos de contacto «Por configurar»: requieren revisión de contenido por el operador, no son una filtración entre empresas.

Evidencias locales: [entorno](b4c4-local-environment.json), [HTTP](b4c4-local-http.json). Rutas `/`, `/shop`, `/admin`, `/admin/website`, `/catalog`, `/login`, `/contact` y `/admin/catalog_admin` responden200 por HTTP;200 de un contenedor administrativo **no demuestra autenticación ni permiso**. API laboral anónima401; dominio desconocido404; localhost funciona con el override explícito de desarrollo. El storefront público y sus respuestas no presentan compra ni enlace operativo wa.me; commerceEnabled=false.

La auditoría READ ONLY al cierre conserva dominio ACTIVE, revisión17,0 publicaciones comerciales y la misma configuración de medios: [estado final](b4c4-local-environment-final.json). Las publicaciones6/7 descritas más abajo corresponden exclusivamente a la base aislada. No se confunden con los datos habituales de demo.localhost.

El [smoke HTTP final habitual](b4c4-local-http-final.json) conserva los200 de contenedores/rutas informativas,401 laboral anónimo y404 de dominio desconocido, después de restaurar el build sin los overrides de integración.

## Pruebas aisladas

`test_apudig_b4c_http` contiene empresas A/B sintéticas y sirve Django8770; Next8771 utiliza esa API mediante variables solo del proceso. El navegador de pruebas emplea `a.b4c.localhost:8771` y `b.b4c.localhost:8771`. Se habilita CORS exclusivamente para esos orígenes locales en el hijo de integración, sin editar `.env`. El build temporal incluye API cliente8770; al cerrar se restaura el build habitual y se retiran procesos/base/contexto sintético.

La fixture representa datos ERP sintéticos persistidos en PostgreSQL, no productos demo utilizados como fallback por Next. La lectura principal pasa por APIs reales. Se conservan las limitaciones de almacenamiento externo simulado; no equivale a R2/CDN real.

| Verificación | Estado / evidencia |
| --- | --- |
| K0–K3, búsqueda, parámetros repetidos, filtros, facets y paginación |11 checks HTTP públicos correctos; [JSON](b4c4-public-http.json) |
| Dominio pendiente/inactivo/desconocido, Website sin publicar, producto ajeno/no publicado |404; aislamiento HTML/RSC A/B y metadata verificados en los checks públicos |
| Precio null y cero, moneda/unidades |Diferenciados; DTO sin costos/proveedores/stock exacto |
| K4–K7, JWT, política ADMIN y referencias ajenas |4 checks HTTP administrativos correctos; [JSON](b4c4-admin-http.json) |
| Home, precio ERP y retirada de destacado |3 checks HTTP correctos;70.80→84.96 sin republicar y retirada inmediata; [JSON](b4c4-home-http.json) |
| Login/refresh/selección Company y perfil actual |Probados con credenciales exclusivamente sintéticas, sin imprimir tokens |
| Guardar borrador, preview privado, publicar banner y metadata SSR |Correcto por API/SSR; no se considera prueba de interacción del formulario React |
| Edición posterior sin publicar |El contenido público anterior permanece |
| 412/428 |No sobrescriben servidor; estado de ambos borradores cliente preservado por la lógica usada en el formulario |
| Editor A cambia a B, donde solo es trabajador |Perfil y navegación no conceden CMS; endpoints deniegan; volver a A recupera las capacidades vigentes |
| Publicación/retirada con CMS y denegación a trabajador |Correcto, sin cambiar Product maestro; catálogo laboral conserva listas/almacenes propios sin compra |
| Stock ERP por unidades sin republicación |Stock8→1: paquete no disponible y base disponible; misma revisión CMS y ETag comercial; [JSON](b4c4-stock-http.json) |

Los5 checks editoriales/roles se guardan en [b4c4-editorial-http.json](b4c4-editorial-http.json). Total HTTP aislado:24 comprobaciones. No se crearon pedidos, ventas, reservas, comprobantes ni movimientos de inventario; únicamente se cambió el saldo de la fixture aislada para comprobar lectura viva.

## Validaciones automáticas

- Lint y build correctos.64 tests Node correctos, incluyendo transporte cancelable, permisos, errores401/403/404/412/428/503 y conservación de trabajo ante conflictos.
- `manage.py check` sin incidencias; `makemigrations --check --dry-run` sin cambios.
-186 pruebas PostgreSQL acotadas correctas: apps.websites, catálogo laboral API/seguridad e imágenes de producto. Cubren impuestos, unidad predeterminada/alternativas, disponibilidad desconocida, listas/almacenes autorizados, publicaciones, concurrencia y namespace/errores de medios. [Evidencia](b4c4-postgresql.json).
- Suite completa727:78 failures y35 errors. **No aprobada globalmente.** Exactamente los mismos casos fallidos del baseline B4-C724; los3 casos añadidos son del ajuste laboral y pasan. [Comparación](b4c4-regression-comparison.json), [casos](b4c4-full-regression.json). Logs detallados en `.tools/b4c4-*.log`, sin publicar credenciales.
- Advertencias previas: baseline-browser-mapping desactualizado y staticfiles ausente en runner. No se instalaron paquetes para silenciarlas.

## Defectos reproducidos y corregidos

1. **Home invitaba a cotizar con commerceEnabled=false.** Reproducido visualmente y con un assert HTTP que falló antes del cambio. StoreHero ahora ofrece «Explorar el catálogo» y enlaza a `/shop`; conserva el comportamiento de cotización solo para un contexto que lo permita. Se cambió «Ilustración de demostración» por «Imagen ilustrativa» para la ilustración editorial publicada. No se activó carrito ni se editó contenido real.
2. **Test administrativo intermitente por paginación.** La fixture buscada no siempre entraba en la primera página ordenada por UUID. El escenario concurrente ahora consulta por su SKU único, sin modificar contrato ni orden del servidor. Se repitió y pasó.
3. **Helper nuevo de stock intentó guardar updated_at inexistente.** Se corrigió para guardar solo quantity; el primer intento retiró limpiamente la base/contexto. Se reconstruyó el entorno aislado y se repitió el caso con éxito. No era un defecto del ERP.
4. **Estado editorial ambiguo tras guardar.** El formulario mostraba «Revision publicada» por existir una publicación anterior, aun cuando el nuevo banner solo estaba en borrador. La evidencia del navegador y de API distinguió revisión de borrador6 de publicación3. Se reutiliza `unapplied` para mostrar «Borrador pendiente de publicación»; no cambia el flujo ni las revisiones. Cambio de presentación incluido en lint/build; recorrido completo de esta etiqueta tras el último build pendiente.

Archivos funcionales de este ajuste: frontend `StoreHero.jsx`, su prop en `StoreHome.jsx` y etiqueta de estado de `WebsiteEditor.jsx`. Pruebas/herramientas: `storefront-http.integration.mjs`, `website-catalog-http.integration.mjs`, nuevos `website-acceptance-http.integration.mjs`, `website-browser-evidence.mjs`, `website-local-audit.mjs`, `audit_local_website.py` y extensión del helper `run_storefront_integration.py` para stock, permisos A/B y CORS local. No se volvió a implementar B4-C.

Hallazgo legado P2: tras seleccionar empresa, AuthContext consulta `/api/v1/auth/store-access/stores/me`, que responde404 y es capturado como ausencia de sucursales. La ruta no está montada en este backend; WebsiteEditor y los permisos de Company sí funcionan y se verificaron con JWT. No se creó una API ERP nueva ni se modificó la autenticación general para ocultar el error. Debe conciliarse ese consumidor heredado antes de usar selección de sucursal en el piloto; no se considera una solución permanente dejarlo sin atender.

## R2/CDN: bloqueado operacionalmente

La configuración efectiva solo tiene R2_PUBLIC_BASE_URL. Faltan R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY y R2_BUCKET_NAME. Ningún secreto se mostró ni modificó. La autorización previa sigue siendo R2 simulado; no se probaron PUT/DELETE reales ni se tocaron objetos productivos. El Website habitual no tiene WebsiteMedia activo ni prefijo persistido.

Las186 pruebas incluyen los casos de medios con cliente externo simulado: PNG/JPEG/WebP, límite5MiB, optimización, miniatura, claves por empresa, checksum, rechazo cruzado, compatibilidad `websites/{websiteId}/media/…`, error503, rollback y limpieza de claves intentadas. Estos resultados prueban contratos y manejo de fallos, **no** entrega de imágenes por CDN.

Para validar almacenamiento real: operador debe facilitar un bucket/credenciales de integración de mínimo alcance y prefijo exclusivo aprobado; configurar sus variables fuera de producción; cargar logo y banner por M1, imagen/miniatura de producto mediante su flujo existente; comprobar200 anónimo, MIME, miniatura, caché y visualización en los tres tamaños; intentar referencia ajena y verificar denegación; leer una clave histórica ya autorizada sin moverla; simular fallo controlado del bucket de integración y conciliar metadatos/objetos huérfanos. La limpieza se limita a objetos de esa prueba autorizada. No copiar secretos a este informe.

## QA visual y manual

La habilidad Windows Computer Use pudo acceder esta vez a una **ventana separada de Chrome**. No se utilizó JavaScript de DevTools para modificar la página ni se sustituyó inspección visual por HTTP. Los controles de dispositivo se operaron por UI. La evidencia visual observada está en la conversación; la matriz siguiente distingue lo observado del recorrido todavía pendiente.

| Caso | Estado real |
| --- | --- |
| Home habitual escritorio1920×945 aprox. de contenido |Observado: header, buscador, nombre empresarial, carrusel y CTA; sin desbordamiento evidente en la zona revisada |
| Home móvil360×800 emulado |Observado: header y búsqueda en dos filas, banner, CTA y beneficios; carrusel pausado encuadra una diapositiva completa |
| Home tablet768×1024 |Observado: header, banner, beneficios y anuncios en viewport; sin desbordamiento evidente |
| Catálogo A tablet768×1024 |Observado:28 resultados, categorías, tarjetas, unidad, precio cero y precio70.80; placeholders neutros sin fotografías reales |
| Detalle precio cero tablet |Observado: unidad,0.00, estado no disponible y pedidos deshabilitados |
| Filtros tablet |Observado: panel completo con categorías/marcas/cuentas, rango monetario y acciones visibles; Escape cierra el diálogo |
| Login y selección Company en Chrome |Correctos con editor sintético; muestra A con rol CMS y B sin roles, dashboard de A sin catálogo interno administrativo |
| Guardar/publicar banner desde WebsiteEditor en Chrome |Correcto: título editado por UI, Guardar borrador recibido por Django y publicación por el botón existente. Borrador6/publicación3 antes de publicar; publicación7 después; HTML anónimo actualizado y B aislado. [Evidencia posterior a acciones reales](b4c4-browser-flow.json) |
| Banner publicado en navegador público |Observado en Chrome sobre `/` de A: título «C4 banner A desde navegador», con commerceEnabled=false y contenido propio; la comprobación HTTP adicional fue anónima |
| Panel comercial con rol CMS |Abierto en Chrome; carga K5/K6 reales y muestra publicaciones/destacados; no muestra campos de política/listas/almacenes; informa que requieren administración de la empresa |
| Teclado Tab completo, foco visible y retorno al disparador |Pendiente de recorrido completo; el indicador de foco de accesibilidad del navegador fue insuficiente para aprobar todo el orden |
| Búsqueda/filtros/orden/paginación mediante UI en los tres tamaños |Pendiente de recorrido completo; contratos y paginación HTTP sí verificados |
| Formularios React con ADMIN/trabajador y conflictos en dos ventanas |Pendiente de interacción completa; flujo editorial del rol CMS sí verificado en Chrome; APIs, repositorios y estado ante conflictos sí verificados |
| Logo, fotos desktop/mobile y miniaturas reales |Bloqueado por R2/configuración; no aprobado con SVG/placeholder |
| Footer/contacto completo, carga/error y lector de pantalla |Pendiente de recorrido visual completo y prueba asistiva; no aprobado por el200 de sus rutas |

Checklist manual restante, sobre la base aislada o una integración aprobada:

1. Abrir A y B en sesiones separadas; registrar identidad, título/canonical, banner y color publicado; desconocido/inactivo debe404. Nunca usar la primera empresa como fallback.
2. Repetir1920×1080,768×1024 y360×800: scroll vertical completo; no scroll horizontal de página; sí rails horizontales deliberados. Revisar header/logo/banner, tarjetas, footer y contacto. Verificar zoom200% y orientación.
3. Buscar PUBLIC-A, aplicar dos marcas y categoría, rango inclusive, limpiar filtros, ordenar precio y pasar a página2; comparar total/facets con API. Probar query inválida y API caída sin datos demo.
4. Abrir producto con precio, sin precio y cero; cambiar base/paquete y verificar importes servidor, moneda e impuestos; sin cantidades exactas, compra o proveedores públicos. Comprobar fotografía/alt cuando exista media autorizada.
5. Usar solo teclado: skip link, buscador, categorías, carrusel, pausar/reanudar, filtros y orden, Tab/Shift+Tab en diálogo, Escape y retorno de foco, paginación y detalle. Registrar foco/contraste y lector de pantalla.
6. ADMIN: WebsiteEditor, borrador, preview, publicar y comprobar en navegador limpio; política con lista/almacenes propios. CMS: selección/publicación con política existente, sin opciones sensibles. Trabajador: dashboard/catálogo laboral y denegación del editor/catálogo privado.
7. Dos editores: guardar con misma revisión, provocar412 y428; ambos formularios permanecen intactos hasta recarga explícita. Repetir cambio de empresa y comprobar que no queden productos/permisos de A en B.
8. Ninguna sesión debe poder hacer pedidos, abrir un WhatsApp operativo, reservar stock o iniciar checkout. Verificar que comercio siga false tras todas las publicaciones.

## Preparación del piloto y B4-D propuesta

| Pendiente | Responsable | Condición de salida |
| --- | --- | --- |
| Configuración comercial del Website habitual |ADMIN de empresa |Lista activa autorizada, moneda/impuesto/unidades revisadas, almacenes propios explícitos y productos seleccionados/publicados; sin activar pedidos |
| Identidad, SEO, contacto y textos reales |Operador CMS |Publicar contenido definitivo y revisar títulos genéricos; no modificar Company fiscal |
| R2/CDN de integración |Operaciones + QA |Pruebas reales de imágenes y aislamiento aprobadas con evidencia |
| Recorrido visual y accesibilidad restante |QA + usuario |Checklist anterior por tamaño/rol completado; no aprobar solo por API |
| Fallos ERP históricos |Equipo ERP |Clasificar y atender separadamente; no ocultarlos ni atribuir su corrección a B4-C4 |
| Aceptación de catálogo consultable |Responsable del piloto |Revisión de permisos/dominio/contenido/medios y matriz de riesgos, con commerceEnabled=false |

**B4-D solo como propuesta:** revisar y aprobar el diseño20 antes de crear cuentas comerciales. Reutilizar User y login; separar autorización CommercialAccount por Company/Customer de membresía laboral; acordar verificación, aprobadores, privacidad/retención y lista comercial por cliente. Después diseñar solicitud comercial persistida e idempotente con precios recalculados y destino WhatsApp del snapshot publicado, sin crear venta/reserva/StockMovement/SalesQuotation automáticamente. No implementar registro público ni ruta /cuenta ni activar comercio como parte de esta aceptación.

## Reproducción y cierre

En consola backend: `.venv/Scripts/python.exe docs/architecture/website-integration/run_storefront_integration.py --serve-isolated`. En una consola de integración frontend: configurar solo para ese proceso `NEXT_PUBLIC_API_V1_URL` y `WEBSITE_API_V1_URL` a `http://127.0.0.1:8770/api/v1`, ejecutar `npm.cmd run build` y `npm.cmd run start -- --port 8771`.

Consola de pruebas frontend:

1. `node tests/storefront-http.integration.mjs ../.tools/b4c-http-context.json ../.tools/b4c4-public-http.json`
2. `node tests/website-catalog-http.integration.mjs ../.tools/b4c-http-context.json ../.tools/b4c4-admin-http.json`
3. En stdin del helper: `{"operation":"price","amount":"12.00"}`; ejecutar `node tests/storefront-home-http.integration.mjs ../.tools/b4c-http-context.json 84.96 ../.tools/b4c4-home-http.json`. Este escenario comprueba revisión1 de la fixture, por lo que va antes de las publicaciones editoriales siguientes.
4. `node tests/website-acceptance-http.integration.mjs` verifica roles/editorial/cambio de empresa y deja la precondición para stock.
5. En helper: `{"operation":"stock","quantity":"1.00"}`; ejecutar `node tests/website-acceptance-http.integration.mjs ../.tools/b4c-http-context.json stock`; restaurar fixture con `{"operation":"stock","quantity":"8.00"}`.
6. Para repetir la evidencia UI: iniciar sesión con el usuario sintético CMS del contexto temporal (no copiar sus tokens/contraseñas al informe), elegir A, editar el título a «C4 banner A desde navegador», guardar; `node tests/website-browser-evidence.mjs draft` verifica persistencia y privacidad sin editar CMS. Publicar mediante el botón de Next y ejecutar el mismo script con `published` para comprobar snapshot/HTML/B.

Al terminar, cerrar la ventana separada de QA y el servidor8771; enviar `{"operation":"stop"}` al helper. La base HTTP, Django8770 y el contexto de credenciales sintéticas fueron retirados; los runners PostgreSQL retiraron su base de tests. Se restaura el build desde una consola sin overrides de integración. Los servidores habituales8000/3000 y los registros habituales no se detuvieron ni editaron. No se guardó la contraseña sintética en el navegador.

Habilidad utilizada para inspección visual: [computer-use SKILL.md](C:/Users/Robert/.codex/plugins/cache/openai-bundled/computer-use/26.1111.21308/skills/computer-use/SKILL.md). Sus capturas/árbol de accesibilidad se utilizaron para interactuar con controles observados; el foco completo de teclado y toda la matriz de tamaños/roles no se declaran aprobados.
