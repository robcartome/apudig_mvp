from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0003_backfill_scoped_store_access"),
    ]

    operations = [
        migrations.AlterField(
            model_name="permission",
            name="action_name",
            field=models.CharField(
                blank=True,
                choices=[
                    ("read", "Leer"),
                    ("manage", "Gestionar"),
                    ("authorize", "Autorizar"),
                    ("sell", "Vender"),
                    ("open", "Abrir"),
                    ("close", "Cerrar"),
                    ("change", "Cambiar"),
                    ("apply", "Aplicar"),
                    ("create", "Crear"),
                    ("issue", "Emitir"),
                    ("consolidate", "Consolidar"),
                    ("void", "Anular"),
                    ("refund", "Devolver"),
                    ("reprint", "Reimprimir"),
                ],
                max_length=30,
            ),
        ),
    ]
