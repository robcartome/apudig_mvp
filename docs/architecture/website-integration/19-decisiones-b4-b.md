# Decisiones previas a la implementación B4-B

17/11/2026. Bases actuales limpias: backend `websites_backend@e3f479f`; frontend `mvp_website@856b711`. No se cambian ramas. Se conserva la política laboral de18 y el dashboard compartido documentado en frontend.

La solicitud adjunta autoriza lista pública explícita, override autorizado, precio null sin fuente autorizada, ausencia de fallback interno, impuestos finales, unidad de venta válida/base, cantidades enteras, almacenes explícitos y stock sin reserva. Los importes se redondean al final con la política monetaria del ERP. El catálogo lee datos comerciales vivos, sin republicar el CMS.

Decisión confirmada por el usuario antes de implementar las escrituras dependientes: **solo ADMIN de empresa y superusuario pueden autorizar listas públicas, overrides y almacenes**. Los permisos CMS permiten seleccionar productos y publicar usando la política ya autorizada; no conceden administración de precios ni lectura de todas las listas/almacenes. Los campos/opciones administrativos sensibles se omiten en respuestas para roles CMS; este ajuste de DTO respecto a16 evita una ampliación de acceso privado.

K4 exige manage.website. Lectura comercial requiere read.website explícito o edición/publicación editorial autorizada; permisos exclusivamente de medios/dominios no dan acceso al catálogo comercial administrativo. Crear/editar un vínculo no publicado exige manage.website; publicar/retirar/editar uno publicado exige manage.website y publish.website. K5 PATCH exige ADMIN de Company/superusuario. En K6/K7, enviar priceListId, incluso para limpiarlo, requiere esa administración. Se reutilizan JWT, membresía y validación de contexto existentes.

ETag comercial opaco del agregado settings/vínculos/M2M, comparado bajo bloqueo de Website. No incluye precios/stock ERP ni editorial_revision. Las respuestas administrativas que incluyen ETag leen datos y huella bajo el mismo bloqueo para evitar combinar una representación anterior con una precondición posterior. Se reutiliza AuditLog dentro de la transacción; no se crea otro historial CMS.

Ordenaciones iniciales: name, name-desc, price-asc, price-desc y featured; discount se rechaza por falta de precio anterior autorizado. Nulos al final; UUID como desempate. Las unidades se identifican por Unit UUID y no aceptan factor del navegador. Una conversión a la propia unidad base con factor distinto de1 no es una unidad comercial válida.

Recomendación única de activación futura: un opt-in persistido en WebsiteCatalogSettings, defaultFalse y auditado. No añadir también un feature flag por Website como autoridad paralela. Esta entrega no agrega ese campo, no implementa activación ni crea una migración sin uso. P1 y la configuración comercial continúan devolviendo commerceEnabled=false. Los K0–K3 permiten verificar las publicaciones comerciales explícitas vía API; no conectan ni habilitan el storefront Next. Antes de activación deben aceptarse B4-B/B4-C, aislamiento, política, dominio, medios/CDN y revisión operativa.

Pendientes de negocio ajenos a B4-B: fracciones por unidad, segmentos/clientes mayoristas, autorización comercial por empresa, consentimiento/retención y solicitudes WhatsApp. Se auditan/diseñan en documento separado; no se implementa registro ni carrito.
