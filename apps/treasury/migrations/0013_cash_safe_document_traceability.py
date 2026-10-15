import apps.treasury.models
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("treasury", "0012_cash_safe_manual_income"),
        ("partners", "0004_documenttype_commercial_fields"),
        ("purchases", "0012_purchase_line_global_discount"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(model_name="cashsafemovement", name="supporting_document_number", field=models.CharField(blank=True, max_length=80)),
        migrations.AddField(model_name="cashsafemovement", name="supplier", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="cash_safe_movements", to="partners.supplier")),
        migrations.AddField(model_name="cashsafemovement", name="purchase_document", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="cash_safe_movements", to="purchases.purchasedocument")),
        migrations.AddField(model_name="cashsafemovement", name="expense_category", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="cash_safe_movements", to="purchases.purchasecategory")),
        migrations.CreateModel(
            name="CashSafeMovementAttachment",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("file", models.FileField(max_length=500, upload_to=apps.treasury.models.cash_safe_attachment_upload_to)),
                ("original_name", models.CharField(max_length=255)),
                ("content_type", models.CharField(max_length=100)),
                ("size", models.PositiveBigIntegerField()),
                ("movement", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="treasury.cashsafemovement")),
                ("uploaded_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="cash_safe_attachments", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "treasury_cash_safe_movement_attachments", "ordering": ("created_at",)},
        ),
    ]
