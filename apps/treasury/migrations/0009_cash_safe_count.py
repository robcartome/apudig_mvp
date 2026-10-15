import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("treasury", "0008_cashsafemovement_authorized_at"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="CashSafeCount",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("count_number", models.CharField(max_length=30)),
                ("counted_at", models.DateTimeField()),
                ("currency", models.CharField(choices=[("PEN", "Soles"), ("USD", "Dólares")], default="PEN", max_length=3)),
                ("theoretical_amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("counted_amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("difference", models.DecimalField(decimal_places=2, max_digits=14)),
                ("denominations", models.JSONField(blank=True, default=dict)),
                ("notes", models.CharField(blank=True, max_length=500)),
                ("status", models.CharField(choices=[("PENDING", "Pendiente de revisión"), ("CLOSED", "Cerrado"), ("REJECTED", "Rechazado")], default="PENDING", max_length=10)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("review_notes", models.CharField(blank=True, max_length=500)),
                ("adjustment_movement", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="cash_safe_count", to="treasury.cashsafemovement")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cash_safe_counts", to="companies.company")),
                ("counted_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="performed_cash_safe_counts", to=settings.AUTH_USER_MODEL)),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_cash_safe_counts", to=settings.AUTH_USER_MODEL)),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cash_safe_counts", to="companies.store")),
            ],
            options={"db_table": "treasury_cash_safe_counts", "ordering": ("-counted_at", "-created_at")},
        ),
        migrations.AddConstraint(model_name="cashsafecount", constraint=models.UniqueConstraint(fields=("company", "count_number"), name="uniq_cash_safe_count_number")),
        migrations.AddConstraint(model_name="cashsafecount", constraint=models.CheckConstraint(condition=models.Q(("counted_amount__gte", 0)), name="cash_safe_count_amount_gte_zero")),
    ]
