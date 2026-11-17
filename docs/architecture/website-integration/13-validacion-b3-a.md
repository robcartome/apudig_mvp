# B3-A — Validación del entorno existente

Actualización posterior: el [informe15](15-cierre-b3-a-y-remediacion-p0.md) observa demo.localhost activo/verificado y acceso público HTTP200. El estado PENDING de este informe es el baseline previo; la aceptación visual/R2 sigue pendiente. Los contratos preparados se detallan en [16](16-contratos-y-politica-b4-b.md).

Fecha: 16/11/2026, America/Lima. Esta entrega audita y valida; no activa B4 ni modifica servicios, modelos o contratos comerciales.

## Estado

**B3-A no está integralmente aceptado.** El Website local está publicado, pero su único dominio `demo.localhost` sigue PENDING. Next usa ese hostname y devuelve 404 correctamente. Faltan verificación/activación explícitas, prueba autenticada del editor en navegador y medios reales autorizados.

No se crearon ni modificaron Websites, dominios, publicaciones, permisos, usuarios o productos en la base habitual. La inspección PostgreSQL se ejecutó en transacciones READ ONLY. No se aplicaron migraciones, cambiaron ramas, editaron `.env`, instalaron dependencias, hicieron commits/pushes o desplegaron aplicaciones.

## Repositorios y configuración real

| Elemento | Estado observado |
|---|---|
| Backend | `websites_backend`, HEAD `9e9eaf5`, árbol inicialmente limpio |
| Frontend | `mvp_website`, HEAD `83eb3ac`, árbol inicialmente limpio |
| Dependencias | Django 5.2.19, DRF 3.18.3, psycopg 3.3.8; Node 22.20.0, Next 16.0.10, React 19.1.0 |
| Base local | PostgreSQL, `apudig_mvp`, localhost:5432; esquema Website compatible e historial consistente |
| Datos Website | 1 Website publicado, 1 dominio PENDING sin principal, 0 productos publicados, 0 políticas de catálogo |
| `.env` frontend | URLs API pública/SSR a `http://127.0.0.1:8000/api/v1`; WEBSITE_DEV_HOSTNAME=`demo.localhost` |
| NODE_ENV | No declarado en ese archivo; el modo efectivo depende del comando que arranca Next |
| R2 backend | URL pública declarada; bucket y credenciales no configurados. No se imprimieron ni copiaron secretos |

Las ramas ya no son las bases develop/57c212a citadas por los informes históricos. Se usaron las ramas actuales sin hacer checkout. La configuración del archivo no prueba qué variables heredó un proceso ya iniciado; se recomienda reiniciarlo después de cambios manuales de entorno.

## Verificaciones de esta entrega

[Resultados HTTP](b3a-http.json), mediante GET sin credenciales ni cuerpos de datos comerciales:

| Petición | Resultado | Alcance de la evidencia |
|---|---|---|
| Django `/login/` | 200 | Página de login disponible, no prueba inicio de sesión |
| Django `/management/websites/` | 302 a login con next | Protección para visitante sin sesión |
| P1 para `demo.localhost` | 404 | El dominio PENDING no permite contenido público |
| P1 para hostname desconocido | 404 | Sin fallback a otra empresa |
| Next `/` | 404 | Coherente con la configuración y el dominio pendiente |
| Next `/login` | 200 | Shell de acceso disponible |
| Next `/admin` | 200 | Shell cliente; AuthGuard debe comprobar sesión, no es prueba de acceso autorizado |
| Next `/catalog` | 200 | Shell heredado conservado, no prueba datos ni operaciones comerciales |

Pruebas Node actuales: **45 correctas**, incluidas resolución local solo en desarrollo, protección en producción, DTOs, conflictos, aislamiento lógico de contenido/SEO y transporte público. Se usan dobles de HTTP en esos casos; no equivalen a navegación real.

Pruebas Django/PostgreSQL de esta entrega: **133 correctas**, resultado en [b3a-tests.json](b3a-tests.json). Se ejecutaron Website y administración de usuarios en `test_apudig_b3a_audit`, separada de `apudig_mvp`. StaticFilesStorage/MD5PasswordHasher se limitaron a memoria del runner y a datos sintéticos; los tests de medios usaron R2 simulado. La base de pruebas se destruyó al finalizar. Django check es correcto. No se reejecutó la suite ERP global: los 84 fallos/36 errores históricos de B2/B3 no se convierten en una aprobación actual por estas pruebas acotadas.

Los informes anteriores de B3 demuestran un flujo HTTP con dos empresas sintéticas en una instancia que ya fue retirada. Esa evidencia se conserva como antecedente, no como prueba de que hoy funciona la sesión visual del entorno habitual.

## Bloqueos y límites

- El acceso de automatización de navegador devolvió `The browser access host is unavailable`; no hubo navegación autenticada, capturas, prueba responsive o teclado. La presencia de una ventana Chrome en el inventario no equivale a un navegador controlable.
- No se introdujeron credenciales ni reutilizaron cookies/tokens de una sesión del usuario. Inicio de sesión, selección de empresa y permisos tienen pruebas automatizadas, pero no se ha demostrado aquí su ciclo desde la UI real.
- El único dominio local está pendiente. La publicación CMS no sustituye su verificación y activación.
- R2 carece de bucket/credenciales en la configuración actual. No se realizaron cargas, borrados o lecturas autenticadas de buckets. La URL CDN configurada por sí sola no prueba su funcionamiento.
- Guardar/publicar/restore y aislamiento A/B se verifican en PostgreSQL de pruebas; edición visual, publicación desde otro navegador e imagen desktop/mobile visible requieren sesión y entorno de navegador disponibles.

## Pasos para cerrar B3-A

1. Entrar con la autenticación existente a Django, seleccionar explícitamente la empresa y revisar su Website en `/management/websites/`. No crear otro Website si ya existe el correcto.
2. Para `demo.localhost`, personal APUDIG documenta su aprovisionamiento local autorizado mediante la verificación manual. Después se activa expresamente y se elige como principal si corresponde. Esto no es una comprobación DNS automática ni publica contenido nuevo.
3. Confirmar las URLs API actuales y ejecutar Next con `npm.cmd run dev` para habilitar el override exclusivo de desarrollo. Abrir localhost:3000 y el dominio local registrado; ambos deben mostrar la misma revisión pública.
4. Con usuario autorizado y empresa seleccionada, editar banner/identidad/contacto/SEO, guardar, comprobar que el público anterior permanece, publicar y revisar desde otro contexto de navegador. Probar falta de permiso, revocación y conflicto412 conservando formulario.
5. Validar una segunda empresa solo con datos de integración autorizados, sin sembrarla automáticamente en la base habitual. Confirmar que contenido y metadata de A no aparecen en B ni en un hostname desconocido.
6. Proporcionar entorno R2 de prueba autorizado y realizar upload/preview/publicación/lectura CDN. Probar fallo de carga y retención de imágenes referenciadas sin tocar claves históricas.
7. Verificar móvil/tablet/escritorio, foco/teclado, imágenes y ausencia de información privada en HTML/RSC. Registrar evidencia antes de aceptar B3-A.

La auditoría B4-A puede completarse sin estos requisitos; B4-B/C/D y commerceEnabled permanecen deshabilitados.
