from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0004_alter_permission_action_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="useroperationalflags",
            name="can_correct_pos_payment",
            field=models.BooleanField(
                default=False,
                verbose_name="Puede corregir medios de pago de ventas POS",
            ),
        ),
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
                    ("correct", "Corregir"),
                ],
                max_length=30,
            ),
        ),
    ]
