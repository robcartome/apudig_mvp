import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("companies", "0010_deduplicate_company_accesses"),
        ("inventory", "0019_movement_sales_document"),
        ("partners", "0004_documenttype_commercial_fields"),
        ("sales", "0014_meansofpayment_kind_and_reference"),
    ]

    operations = [
        migrations.CreateModel(
            name="PosRegister",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("code", models.CharField(max_length=30)),
                ("name", models.CharField(max_length=120)),
                ("active", models.BooleanField(default=True)),
                ("ticket_series", models.CharField(default="T", max_length=10)),
                ("current_ticket_number", models.PositiveBigIntegerField(default=0, editable=False)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pos_registers", to="companies.company")),
                ("default_customer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pos_registers", to="partners.customer")),
                ("default_document_type", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pos_registers", to="partners.documenttype")),
                ("default_price_list", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pos_registers", to="inventory.pricelist")),
                ("default_warehouse", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pos_registers", to="inventory.warehouse")),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pos_registers", to="companies.store")),
            ],
            options={
                "db_table": "pos_registers",
                "ordering": ("store_id", "code"),
                "constraints": [models.UniqueConstraint(fields=("company", "store", "code"), name="uniq_pos_register_code")],
            },
        ),
        migrations.CreateModel(
            name="CashSession",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("OPEN", "Abierta"), ("CLOSED", "Cerrada")], default="OPEN", max_length=10)),
                ("opened_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("opening_total", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("opening_note", models.CharField(blank=True, max_length=500)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("expected_cash_total", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("counted_cash_total", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("cash_difference", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("next_opening_total", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("closing_note", models.CharField(blank=True, max_length=500)),
                ("version", models.PositiveIntegerField(default=1)),
                ("closed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="closed_cash_sessions", to=settings.AUTH_USER_MODEL)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cash_sessions", to="companies.company")),
                ("difference_authorized_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="authorized_cash_session_differences", to=settings.AUTH_USER_MODEL)),
                ("opened_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="opened_cash_sessions", to=settings.AUTH_USER_MODEL)),
                ("register", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cash_sessions", to="pos.posregister")),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cash_sessions", to="companies.store")),
            ],
            options={
                "db_table": "pos_cash_sessions",
                "ordering": ("-opened_at",),
                "constraints": [
                    models.UniqueConstraint(condition=models.Q(status="OPEN"), fields=("register",), name="uniq_open_cash_session_per_register"),
                    models.CheckConstraint(condition=models.Q(opening_total__gte=0), name="cash_session_opening_gte_zero"),
                    models.CheckConstraint(condition=models.Q(next_opening_total__isnull=True) | models.Q(next_opening_total__gte=0), name="cash_session_next_opening_gte_zero"),
                ],
            },
        ),
        migrations.CreateModel(
            name="CashDenominationCount",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("phase", models.CharField(choices=[("OPENING", "Apertura"), ("CLOSING", "Cierre")], max_length=10)),
                ("denomination", models.DecimalField(decimal_places=2, max_digits=14)),
                ("quantity", models.PositiveIntegerField()),
                ("total", models.DecimalField(decimal_places=2, max_digits=14)),
                ("cash_session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="denomination_counts", to="pos.cashsession")),
            ],
            options={
                "db_table": "pos_cash_denomination_counts",
                "ordering": ("phase", "-denomination"),
                "constraints": [
                    models.UniqueConstraint(fields=("cash_session", "phase", "denomination"), name="uniq_cash_denomination_per_phase"),
                    models.CheckConstraint(condition=models.Q(denomination__gt=0), name="cash_denomination_gt_zero"),
                    models.CheckConstraint(condition=models.Q(total__gte=0), name="cash_denomination_total_gte_zero"),
                ],
            },
        ),
        migrations.CreateModel(
            name="CashMovement",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("movement_type", models.CharField(choices=[("PAY_IN", "Ingreso"), ("PAY_OUT", "Egreso"), ("WITHDRAWAL", "Retiro"), ("DEPOSIT", "Deposito")], max_length=20)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("reason_code", models.CharField(blank=True, max_length=40)),
                ("description", models.CharField(max_length=500)),
                ("authorized_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="authorized_pos_cash_movements", to=settings.AUTH_USER_MODEL)),
                ("cash_session", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cash_movements", to="pos.cashsession")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_pos_cash_movements", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "pos_cash_movements",
                "ordering": ("created_at",),
                "constraints": [models.CheckConstraint(condition=models.Q(amount__gt=0), name="cash_movement_amount_gt_zero")],
            },
        ),
        migrations.CreateModel(
            name="PosTransaction",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("DRAFT", "Borrador"), ("PAYMENT_PENDING", "Pago pendiente"), ("PROCESSING", "Procesando"), ("COMPLETED", "Completada"), ("CANCELLED", "Cancelada"), ("FAILED", "Fallida")], default="PROCESSING", max_length=20)),
                ("billing_status", models.CharField(choices=[("NOT_REQUESTED", "No solicitada"), ("INVOICE_REQUESTED", "Solicitada"), ("INVOICE_PROCESSING", "Procesando"), ("INVOICED", "Facturada"), ("INVOICE_FAILED", "Fallida")], default="NOT_REQUESTED", max_length=25)),
                ("idempotency_key", models.UUIDField()),
                ("ticket_number", models.PositiveBigIntegerField()),
                ("ticket_code", models.CharField(max_length=30)),
                ("device_identifier", models.CharField(blank=True, max_length=120)),
                ("started_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("failure_code", models.CharField(blank=True, max_length=60)),
                ("failure_message", models.CharField(blank=True, max_length=500)),
                ("cash_session", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transactions", to="pos.cashsession")),
                ("cashier", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pos_transactions", to=settings.AUTH_USER_MODEL)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="pos_transactions", to="companies.company")),
                ("register", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transactions", to="pos.posregister")),
                ("sales_document", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="pos_transaction", to="sales.salesdocument")),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="pos_transactions", to="companies.store")),
            ],
            options={
                "db_table": "pos_transactions",
                "ordering": ("-started_at",),
                "constraints": [
                    models.UniqueConstraint(fields=("company", "register", "idempotency_key"), name="uniq_pos_idempotency_key"),
                    models.UniqueConstraint(fields=("register", "ticket_number"), name="uniq_pos_ticket_number"),
                ],
            },
        ),
        migrations.CreateModel(
            name="SalesPayment",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("REGISTERED", "Registrado"), ("CANCELLED", "Cancelado"), ("REFUNDED", "Devuelto")], default="REGISTERED", max_length=15)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("currency", models.CharField(default="PEN", max_length=3)),
                ("exchange_rate", models.DecimalField(decimal_places=6, default=1, max_digits=10)),
                ("amount_in_sale_currency", models.DecimalField(decimal_places=2, max_digits=14)),
                ("received_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("change_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("operation_reference", models.CharField(blank=True, max_length=120)),
                ("paid_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("cash_session", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sales_payments", to="pos.cashsession")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_pos_payments", to=settings.AUTH_USER_MODEL)),
                ("means_of_payment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="pos_payments", to="sales.meansofpayment")),
                ("sales_document", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="pos_payments", to="sales.salesdocument")),
            ],
            options={
                "db_table": "pos_sales_payments",
                "ordering": ("paid_at",),
                "constraints": [
                    models.CheckConstraint(condition=models.Q(amount__gt=0), name="pos_payment_amount_gt_zero"),
                    models.CheckConstraint(condition=models.Q(exchange_rate__gt=0), name="pos_payment_exchange_rate_gt_zero"),
                    models.CheckConstraint(condition=models.Q(amount_in_sale_currency__gt=0), name="pos_payment_sale_amount_gt_zero"),
                    models.CheckConstraint(condition=models.Q(received_amount__gte=0), name="pos_payment_received_gte_zero"),
                    models.CheckConstraint(condition=models.Q(change_amount__gte=0), name="pos_payment_change_gte_zero"),
                ],
            },
        ),
        migrations.CreateModel(
            name="CashTenderDeclaration",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("expected_amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("counted_amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("difference", models.DecimalField(decimal_places=2, max_digits=14)),
                ("cash_session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tender_declarations", to="pos.cashsession")),
                ("means_of_payment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cash_declarations", to="sales.meansofpayment")),
            ],
            options={
                "db_table": "pos_cash_tender_declarations",
                "constraints": [
                    models.UniqueConstraint(fields=("cash_session", "means_of_payment"), name="uniq_cash_tender_declaration"),
                    models.CheckConstraint(condition=models.Q(expected_amount__gte=0), name="cash_tender_expected_gte_zero"),
                    models.CheckConstraint(condition=models.Q(counted_amount__gte=0), name="cash_tender_counted_gte_zero"),
                ],
            },
        ),
        migrations.CreateModel(
            name="SalesDocumentSource",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("source_kind", models.CharField(choices=[("POS_TICKET", "Ticket POS")], default="POS_TICKET", max_length=20)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_sales_document_links", to=settings.AUTH_USER_MODEL)),
                ("source_document", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="target_document_links", to="sales.salesdocument")),
                ("target_document", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="source_document_links", to="sales.salesdocument")),
            ],
            options={
                "db_table": "pos_sales_document_sources",
                "constraints": [
                    models.UniqueConstraint(fields=("source_document",), name="uniq_invoiced_pos_ticket"),
                    models.CheckConstraint(condition=~models.Q(source_document=models.F("target_document")), name="pos_source_differs_from_target"),
                ],
            },
        ),
    ]
