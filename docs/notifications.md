# Centro de notificaciones

`python manage.py sync_notifications` ejecuta una sincronizacion puntual de los
avisos empresariales. Actualmente revisa las cuotas pendientes de documentos de
compra a credito, crea o actualiza un aviso por cuota, asigna como destinatarios
a los usuarios con permiso `read.purchases.documents` y resuelve el aviso cuando
la deuda deja de estar pendiente. El comando es idempotente: volver a ejecutarlo
no duplica avisos.

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
