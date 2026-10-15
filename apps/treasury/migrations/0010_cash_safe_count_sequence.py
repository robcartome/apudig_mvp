from django.db import migrations, models


def backfill_sequences(apps, schema_editor):
    CashSafeCount = apps.get_model("treasury", "CashSafeCount")
    counters = {}
    counts = CashSafeCount.objects.order_by("company_id", "counted_at", "created_at", "id")
    for count in counts.iterator():
        key = (count.company_id, count.counted_at.year, count.counted_at.month)
        counters[key] = counters.get(key, 0) + 1
        count.sequence_number = counters[key]
        count.count_number = (
            f"ARQ-{count.counted_at:%Y%m}-{count.sequence_number:04d}"
        )
        count.save(update_fields=("sequence_number", "count_number"))


class Migration(migrations.Migration):
    dependencies = [("treasury", "0009_cash_safe_count")]
    operations = [
        migrations.AddField(
            model_name="cashsafecount",
            name="sequence_number",
            field=models.PositiveBigIntegerField(null=True),
        ),
        migrations.RunPython(backfill_sequences, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="cashsafecount",
            name="sequence_number",
            field=models.PositiveBigIntegerField(),
        ),
    ]
