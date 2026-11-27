# Centro de notificaciones

## Consulta del contador y campana

El navegador no realiza sondeos periódicos. Guarda únicamente el contador y su
fecha de actualización en `localStorage`, separados por usuario, empresa y
sucursal, durante un máximo de 6 horas. Al cargar una página consulta
`unread-count/` solo si no existe un contador vigente para ese contexto. Volver
a una pestaña visible no provoca consultas adicionales.

Abrir la campana siempre consulta `dropdown/` sin caché HTTP y actualiza tanto
la lista como el contador. Las acciones de lectura también actualizan el
contador; las otras pestañas del mismo contexto reciben el cambio mediante el
evento `storage`, sin otra petición. Si el almacenamiento está bloqueado, las
consultas se hacen únicamente cuando el usuario interactúa con la campana.

Las peticiones incluyen el usuario, empresa y sucursal que muestra la página.
Si el contexto de sesión cambió en otra pestaña, el servidor rechaza la petición
con HTTP 404 y es necesario recargar esa página. Esto evita mostrar o marcar
notificaciones de otro contexto. La caché afecta al contador visual, no a los
permisos ni a la generación de avisos.

Pruebas de servidor y del comportamiento de caché del navegador (sin
dependencias JavaScript adicionales):

```bash
python manage.py test apps.notifications --settings=config.settings_test
node --test apps/notifications/tests/test_notifications_js.cjs
```

## Generación de avisos

`python manage.py sync_notifications` ejecuta una sincronizacion puntual de los
avisos empresariales. Actualmente revisa las cuotas pendientes de documentos de
compra a crédito o con pago diferido. También incluye documentos antiguos sin condición
de pago que tengan un vencimiento explícito y saldo pendiente. Crea o actualiza
un aviso por cuota, asigna como destinatarios
a los usuarios con permiso `read.purchases.documents` y resuelve el aviso cuando
la deuda deja de estar pendiente. El comando es idempotente: volver a ejecutarlo
no duplica avisos.

Los indicadores `is_credit=True` o `immediate_payment=False` identifican pagos
diferidos. Una condición inmediata sin crédito no genera estos avisos, aunque
no sea efectivo. La deuda se calcula con los
pagos registrados, incluyendo pagos parciales; no se deduce del nombre de la
condición. Un documento sin condición ni vencimiento explícito no genera un
aviso de vencimiento usando una fecha supuesta.

Después de desplegar esta corrección, ejecutar una sincronización para incluir
los documentos antiguos sin modificar sus condiciones ni registrar pagos.

Puede limitarse a un contexto concreto:

```bash
python manage.py sync_notifications
python manage.py sync_notifications --company <uuid-empresa>
python manage.py sync_notifications --store <uuid-sucursal>
```

Como el vencimiento cambia con el calendario, en produccion este comando debe
programarse periodicamente (por ejemplo, cada 30 minutos con cron o el scheduler
de la plataforma). Los cambios de un documento o pago tambien solicitan una
sincronizacion inmediata al confirmar la transaccion.

Antes de iniciar una version nueva deben ejecutarse las migraciones, recopilarse
los estaticos y hacerse al menos una sincronizacion:

```bash
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py sync_notifications
```

La imagen Docker ejecuta esos tres pasos mediante `docker-entrypoint.sh` antes
de iniciar la aplicacion. Esto cubre el despliegue y los reinicios, pero no
reemplaza la ejecucion periodica del comando.
