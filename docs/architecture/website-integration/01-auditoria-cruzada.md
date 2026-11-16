# 01 — Auditoría cruzada del website APUDIG

Fecha: 15/11/2026, America/Lima. Estado: auditoría y diseño; sin implementación funcional.

## Alcance y evidencia

| Fuente | Estado observado |
|---|---|
| Backend `apudig_mvp` | Rama `develop`, HEAD `c8296b7`; modificación previa en `.gitignore` preservada |
| Frontend `ad_frontend` | Rama `mvp_website`, HEAD `57c212a`; árbol inicialmente limpio |
| Referencia backend | Rama local `websites_v0`, commit `a9d3a3a`; comparación `develop...websites_v0`: 0 commits exclusivos de develop y 1 de websites_v0 |
| Otra rama local | `feature/website-cart-whatsapp-phase-5` apunta a `c8296b7`; su nombre no demuestra funcionalidad adicional |

Se inspeccionaron fuentes locales e historial Git mediante `git show`, sin checkout, merge, fetch, commit ni push. El commit histórico modifica 42 archivos: no es una unidad pequeña para recuperar a ciegas. La auditoría no acredita el estado de servidores ni ramas remotas actuales.

No se consultaron credenciales, bases de datos ni infraestructura productiva. No se verificaron tablas o registros de `django_migrations`. `config/settings.py` admite configurar el motor y usa SQLite por defecto; `config/settings_test.py` usa SQLite en memoria. Por tanto, la existencia de configuración PostgreSQL no demuestra que esta sesión esté usando PostgreSQL.

## Conclusión

Next tiene una web comercial y un CMS local avanzados; Django develop tiene ERP, autenticación y catálogos previos. La integración editorial y comercial nueva no está activa. Hay dominio CMS recuperable en websites_v0, pero sus contratos y semántica de publicación necesitan adaptación.

Primera entrega posterior recomendada: Website + dominio seguro + borrador/publicación de banner + lectura pública desde PostgreSQL, visible en un segundo navegador sin depender de localStorage. Catálogo y cotizaciones quedan para B4/B5. Ver [plan](07-plan-implementacion.md).

## Frontend: pantallas, fuentes y límites

Rutas relativas al repositorio `ad_frontend`. DEMO = `src/data/demo/storefront.js`; LOCAL = almacenamiento del navegador; API = servicio existente, sin validación HTTP integrada en esta auditoría.

| Pantalla | Componentes / ubicación | Servicio o fuente real | Clasificación y límite |
|---|---|---|---|
| `/` | `src/app/(public)/page.js`, `StoreHome`, `StoreHero` | `src/lib/storefront/store.js`; defaults de `createWebsiteDocument` | DEMO; el Home no recibe el borrador local ni contenido publicado de Django |
| Header/footer | `(public)/layout.js`, `StoreHeader`, `StoreFooter` | `getStore`, `getStorefrontCategories` | DEMO; identidad, contacto y navegación no se resuelven por dominio real |
| `/shop` | `(public)/shop/page.js`, `StoreCatalog` | `getStorefrontProducts`, `shop-filters.mjs` | DEMO; filtrado, facets y paginación en memoria sobre el conjunto completo |
| `/shop/[id]` | `(public)/shop/[id]/page.js`, `ProductPurchase` | `getStorefrontProduct`; relacionados del array completo | DEMO; genera metadata local y 404 para ID ausente |
| `/about` | `(public)/about/page.js` | `getStore` + textos escritos en JSX | DEMO y hardcodeado; el editor no ofrece un cuerpo completo de historia corporativa |
| `/contact` | `(public)/contact/page.js` | `getStore`, helpers de contacto | DEMO + textos de plantilla; no hay formulario de envío ni API de contactos implementados |
| `/cart` y panel | `CartPage`, `CartProvider`, `CartDrawer`, `CartItem` | `src/lib/commerce/cart.mjs` | LOCAL + productos DEMO; guarda IDs/cantidades/notas y recalcula desde el array disponible |
| WhatsApp | `quotationUrl`, `buildQuotationMessage` | Módulo `cart.mjs` | Enlace preparado; bloqueado por `mode: demo` y falta de número válido; no crea documentos ERP |
| `/admin/website` | `WebsiteAccess`, `WebsiteEditor`, `ShowcaseEditor`, `WebsiteFields` | `createLocalWebsiteRepository` | LOCAL por empresa/web; validación contra IDs demo |
| Preview | `WebsitePreview`, iframe y postMessage | Repositorio LOCAL y documento del formulario | LOCAL, protegida por guard/permisos cliente; no sustituye autorización DRF |
| Login/empresa | `AuthContext`, `authService.js`, `AuthGuard` | `/api/v1/auth/*` | API existente; renovación, roles y empresa necesitan regresión real |
| `/catalog` y `/admin/catalog_admin` | `CatalogPage`, modal y tarjetas administrativos | `productsService.js`, `api.js`, API catalog pública/privada | API previa que se debe preservar; no son las rutas del nuevo storefront |
| Antiguas vistas ERP Next | `src/lib/admin/routes.mjs`, `ErpModuleNotice` | Vista de transición a Django | Archivos históricos conservados; no reactivar sus servicios como alcance implícito |

`StoreHome` conserva beneficios y textos de presentación en JSX: no todos los textos visibles son editables. Header posee enlaces de plantilla; no existe editor completo de menús en Next. Categorías destacadas por ID no son una selección editorial configurable actual: la navegación proviene del array de categorías y los destacados muestran productos por categoría.

### Servicios preparados, no conectados

- `storefrontProductsService.mjs` / `storefrontCategoriesService.mjs`: factorías públicas sin token, con `credentials: omit`, `no-store` y validación de `store_id`; esperan rutas `/stores/{storeId}/...` todavía no implementadas.
- `websiteRepository.mjs:createDjangoWebsiteRepository`: prepara lectura/editor, PUT draft y POST publish con If-Match; `WebsiteEditor` y `WebsitePreview` instancian exclusivamente el repositorio local.
- `api.js`: cliente administrativo con JWT desde localStorage; descarta status/código/campos de errores al crear un Error genérico. No usar como transporte público SSR.
- `storeAccessService.js`: llama `/auth/store-access/...` y `/stores/{id}`, no montados en la API v1 inspeccionada. `AuthContext` captura parte de esos fallos: no confundir con sucursales operativas.

### Contrato editorial real

Autoridad frontend: `src/lib/website/content.mjs`, `WEBSITE_SCHEMA_VERSION = 3`, `validateWebsite`, `upgradeWebsiteDocument`.

| Grupo | Estructura y validación actual |
|---|---|
| identity | name 100, shortName 40, location 100, primaryColor #RRGGBB, logoUrl, announcement 180 |
| contact | phone 40, secondaryPhone opcional 40, email opcional 180, whatsapp 8–15 dígitos, address 300, hours 180; socials opcionales HTTPS por proveedor |
| seo | title 70 y description 180, obligatorios |
| heroSlider | Opcional; autoplay boolean, intervalMs entero 3000–15000; default frontend 6000 |
| banners | Máximo 12; ID estable, visibilidad, eyebrow 60, título 100, descripción 300, CTA 40, href interno, imágenes desktop/mobile y alt 180 |
| announcements | CTA general conservado por compatibilidad y hasta 8 items; título, descripción opcional 180, CTA opcional 40, badge 40/posición, imagen/alt |
| specials | Hasta 4 productIds únicos y de la fuente autorizada |
| promotions | Hasta 12; fechas ISO UTC, fin posterior al inicio, hasta 50 IDs únicos por campaña; no son reglas de precio |
| sections | Exactamente una por tipo: benefits/categories/announcements/specials/featured/promotions/about; orden del array, enabled, título 100 |

`categories` se conserva por compatibilidad v3; no debe duplicar la navegación ni controlar su visibilidad. Los documentos v1/v2 se adaptan al leer. El contenedor local continúa con clave v1, independiente del esquema editorial.

Imágenes locales de banners/avisos: PNG/JPEG/WebP originales de hasta 8 MiB, optimizados en navegador a data URL de hasta 150 KiB. No son media Django. Backend actual limita productos por defecto a 5 MiB: hay que armonizar límites, subir por canal de media y rechazar data URLs editoriales en API.

### Carrito real

`cart.mjs`: clave `apudig:quotation:{storeId}:v1`, payload `{version,storeId,items:[{id,quantity,notes?}]}`, cantidades enteras 1–999, observaciones 240 caracteres. La validación conserva hasta 200 líneas; el endpoint histórico admite 50. Precios no se persisten como autoridad; moneda visual PEN fija. El contrato de cotización futura debe documentar estos límites y la unidad comercial.

La restauración descarta IDs que no están en el array recibido. Conectar solo una página API al provider eliminaría líneas válidas de otras páginas: B5 debe resolver productos por IDs, separadamente de `/shop`.

## Backend develop: recursos aprovechables

| Dominio | Fuente / símbolo | Situación |
|---|---|---|
| Empresa | `apps/companies/models.py:Company`, UUID | Identidad fiscal y contacto ERP; no sobrescribir desde el CMS |
| Sucursal | `Store.company` | Una empresa tiene sucursales; Website no equivale a Store |
| Acceso | `UserCompanyAccess`, `ActiveCompanyMiddleware` | Acceso usuario/empresa/sucursal y validación de contexto de sesión |
| JWT | `apps/api/v1/users/helpers.py:make_token_pair`, `auth/tokens.py`, `authentication.py:JWTAuthentication` | Claims company/store/roles/permisos; autenticación JWT por sí sola no revalida membresía actual |
| Permisos | `apps/users/models.py:Permission`, `apps/users/permissions.py` | Sistema propio acción.módulo; usar asignación explícita y comprobación de membresía |
| Productos | `apps/inventory/models.py:Product`, Category, Brand | Maestros existentes; Company nullable en algunas entidades, excluir filas sin empresa de la web |
| Presentaciones | ProductUnit / Unit | Conversión y precio opcional por presentación; web actual solo maneja una unidad textual |
| Precios | PriceList / ProductPrice, `apps/inventory/pricing.py` | Reutilizar resolvedor y Decimal; metadatos fiscales sin doble IGV |
| Existencias | Warehouse, StockByWarehouse | Warehouse pertenece a Company mediante `store__company`; publicar disponibilidad, no cantidades internas |
| Imágenes | `apps/inventory/product_image_storage.py` | R2, inspección Pillow, optimización WebP, thumbnails y URLs públicas |
| Ventas | `apps/sales/models.py:SalesQuotation`, SaleOrder, SalesDocument; `services.py:create_quotation` | Cotización ERP exige cliente y servicio requiere serie/sucursal; no equivale a carrito anónimo |
| CMS | `apps/websites` en develop | Solo artefactos compilados; sin fuentes .py, app instalada ni URLs CMS en las fuentes actuales |

APIs actuales: `apps/api/v1/urls.py` monta catalog, inventory, users, sales, pos y companies. `sales/urls.py` y `companies/urls.py` están vacíos; v2 es placeholder. La API POS existe, con contrato operativo distinto al website.

### Hallazgos prioritarios de seguridad y compatibilidad

1. **Consultas globales posibles por ausencia de tenant:** catálogo público AllowAny y `company_required=False`; `get_products(company_id=None)` no filtra Company y `filter_by_company(qs, None)` devuelve qs íntegro. Evidencia estática; no se ejecutó extracción HTTP de datos.
2. **Exposición administrativa:** `ProductListAPIView` y `ProductDetailAPIView` de inventory usan AllowAny en develop. Revisar sus serializers y consumidores antes de endurecerlos; no construir el storefront sobre ellos.
3. **DTO público heredado demasiado amplio:** catálogo detalle entrega stock por almacén y listas de precios; lista/detalle entregan códigos de proveedor. Omitir price_purchase no convierte esta respuesta en el DTO comercial requerido.
4. **Autorización incompleta como base CMS:** `IsCompanyUser` actual comprueba presencia de contexto, no membresía; `user_has_company_permission` conserva acceso legado si un módulo no tiene permisos configurados. Nueva API debe denegar por defecto.
5. **Logout:** `LogoutAPIView` es noop stateless. El comentario frontend que dice revocar refresh no es evidencia de revocación. No se propone rehacer autenticación para esta primera entrega; documentar límite.
6. **Regresión al recuperar websites_v0:** el endpoint heredado público pasa a exigir `?site=`; Next existente no lo envía. Cambia también autorización de inventory. No recuperar esos cambios sin contrato de compatibilidad.

## Verificaciones y límites

En esta conversación se ejecutaron 40 pruebas Node de commerce/website/admin-routes/storefront-api/contact/shop-filters y lint: correctos. No acreditan Django, PostgreSQL ni dominios reales. Builds/smokes/QA de documentos frontend son históricos; las entregas recientes mantienen QA visual pendiente. No se ejecutaron build, tests Django, migraciones, validación de PostgreSQL o navegador integrado en esta auditoría documental.

Se leyeron los cinco documentos de `ad_frontend/docs`. Algunos encabezados aún citan mvp_production y fechas previas: prevalecen las ramas verificadas arriba. No se modificó documentación frontend.

## Lectura del paquete

1. [Comparación websites_v0](02-comparacion-websites-v0.md).
2. [Arquitectura](03-arquitectura-website-backend.md).
3. [Datos y migraciones](04-modelo-datos-y-migraciones.md).
4. [Contratos y matriz por pantalla](05-contratos-api-frontend.md).
5. [Seguridad multiempresa](06-seguridad-multiempresa.md).
6. [Plan B0–B6](07-plan-implementacion.md).
7. [Pruebas y aceptación](08-matriz-pruebas.md).
