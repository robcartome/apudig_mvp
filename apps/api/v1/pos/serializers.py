from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Sum
from django.urls import reverse
from rest_framework import serializers

from apps.pos.models import CashSession, PosRegister, PosReturn, PosTransaction, SalesPayment
from apps.sales.models import SalesDocumentLine


class PosRegisterSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source="store.name", read_only=True)
    default_warehouse_name = serializers.CharField(
        source="default_warehouse.name", read_only=True, allow_null=True
    )
    default_price_list_name = serializers.CharField(
        source="default_price_list.name", read_only=True, allow_null=True
    )
    default_customer_name = serializers.CharField(
        source="default_customer.legal_name", read_only=True, allow_null=True
    )
    default_customer_document_number = serializers.CharField(
        source="default_customer.document_number", read_only=True, allow_null=True
    )
    default_customer_address = serializers.CharField(
        source="default_customer.address", read_only=True, allow_null=True
    )
    default_document_type_code = serializers.CharField(
        source="default_document_type.code", read_only=True, allow_null=True
    )

    class Meta:
        model = PosRegister
        fields = (
            "id", "code", "name", "store_name", "active", "ticket_series",
            "default_warehouse", "default_warehouse_name",
            "default_price_list", "default_price_list_name",
            "default_customer", "default_customer_name",
            "default_customer_document_number", "default_customer_address",
            "default_document_type", "default_document_type_code",
        )


class CashSessionSerializer(serializers.ModelSerializer):
    register_code = serializers.CharField(source="register.code", read_only=True)
    opened_by_name = serializers.CharField(source="opened_by.display_name", read_only=True)

    class Meta:
        model = CashSession
        fields = (
            "id", "register", "register_code", "session_number", "currency", "status", "opened_at", "opened_by_name",
            "opening_total", "opening_note", "closed_at", "expected_cash_total",
            "counted_cash_total", "cash_difference", "next_opening_total",
            "safe_deposit_total", "bank_deposit_total", "bank_deposit_destination",
            "closing_note", "version",
        )


class SalesPaymentSerializer(serializers.ModelSerializer):
    means_of_payment_name = serializers.CharField(source="means_of_payment.name", read_only=True)
    means_of_payment_kind = serializers.CharField(source="means_of_payment.kind", read_only=True)

    class Meta:
        model = SalesPayment
        fields = (
            "id", "means_of_payment", "means_of_payment_name", "means_of_payment_kind",
            "status", "amount", "currency", "exchange_rate", "amount_in_sale_currency",
            "received_amount", "change_amount", "operation_reference", "paid_at",
        )


class PosReceiptLineSerializer(serializers.ModelSerializer):
    returned_quantity = serializers.SerializerMethodField()
    is_manual = serializers.SerializerMethodField()
    product_id = serializers.UUIDField(read_only=True)
    unit_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = SalesDocumentLine
        fields = (
            "id", "product_id", "description", "product_code", "unit_id", "unit_code",
            "quantity", "unit_price", "discount_amount", "tax_type", "igv_rate",
            "memo", "total", "returned_quantity", "is_manual",
        )

    def get_returned_quantity(self, obj):
        value = obj.pos_return_lines.filter(
            pos_return__status=PosReturn.Status.COMPLETED
        ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
        return str(value)

    def get_is_manual(self, obj):
        return obj.product.sku == "VARIOS-POS"


class PosTransactionSerializer(serializers.ModelSerializer):
    sales_document_id = serializers.UUIDField(source="sales_document.pk", read_only=True)
    document_type = serializers.CharField(source="sales_document.document_type.code", read_only=True)
    document_series = serializers.CharField(source="sales_document.series_code", read_only=True)
    document_number = serializers.CharField(source="sales_document.number", read_only=True)
    customer_id = serializers.UUIDField(source="sales_document.customer_id", read_only=True, allow_null=True)
    customer_name = serializers.CharField(source="sales_document.customer_legal_name", read_only=True)
    customer_document_type = serializers.CharField(source="sales_document.customer_document_type", read_only=True)
    customer_document_number = serializers.CharField(source="sales_document.customer_document_number", read_only=True)
    customer_address = serializers.CharField(source="sales_document.customer_address", read_only=True)
    currency = serializers.CharField(source="sales_document.currency", read_only=True)
    subtotal = serializers.DecimalField(
        source="sales_document.subtotal", max_digits=14, decimal_places=2, read_only=True
    )
    igv_total = serializers.DecimalField(
        source="sales_document.igv_total", max_digits=14, decimal_places=2, read_only=True
    )
    total_discount = serializers.DecimalField(
        source="sales_document.total_discount", max_digits=14, decimal_places=2, read_only=True
    )
    total = serializers.DecimalField(
        source="sales_document.total", max_digits=14, decimal_places=2, read_only=True
    )
    due_date = serializers.DateField(source="sales_document.due_date", read_only=True)
    paid_amount = serializers.SerializerMethodField()
    outstanding_amount = serializers.SerializerMethodField()
    payments = SalesPaymentSerializer(source="sales_document.pos_payments", many=True, read_only=True)
    lines = PosReceiptLineSerializer(source="sales_document.lines", many=True, read_only=True)
    document_pdf_url = serializers.SerializerMethodField()
    electronic_status = serializers.SerializerMethodField()
    electronic_message = serializers.CharField(
        source="sales_document.sunat_response_message", read_only=True
    )
    qr_payload = serializers.SerializerMethodField()
    price_list_id = serializers.UUIDField(source="sales_document.price_list_id", read_only=True, allow_null=True)
    payment_method_id = serializers.UUIDField(source="sales_document.payment_method_id", read_only=True, allow_null=True)
    global_discount_amount = serializers.DecimalField(
        source="sales_document.global_discount_amount", max_digits=14, decimal_places=2, read_only=True
    )
    global_discount_before_tax = serializers.BooleanField(
        source="sales_document.global_discount_before_tax", read_only=True
    )
    notes = serializers.CharField(source="sales_document.notes", read_only=True)
    cashier_name = serializers.SerializerMethodField()
    register_name = serializers.CharField(source="register.name", read_only=True)
    company_name = serializers.SerializerMethodField()
    company_ruc = serializers.SerializerMethodField()
    company_address = serializers.SerializerMethodField()
    company_phone = serializers.SerializerMethodField()
    company_email = serializers.SerializerMethodField()
    company_logo_url = serializers.SerializerMethodField()
    store_name = serializers.SerializerMethodField()
    store_address = serializers.SerializerMethodField()

    class Meta:
        model = PosTransaction
        fields = (
            "id", "idempotency_key", "ticket_code", "ticket_number", "status", "billing_status",
            "payment_condition", "payment_status", "due_date",
            "cash_session", "register", "register_name", "cashier", "cashier_name", "started_at", "completed_at",
            "company_name", "company_ruc", "company_address", "company_phone",
            "company_email", "company_logo_url", "store_name", "store_address",
            "sales_document_id", "document_type", "document_series", "document_number",
            "customer_id", "customer_name", "customer_document_type",
            "customer_document_number", "customer_address", "currency", "subtotal", "igv_total",
            "price_list_id", "payment_method_id", "global_discount_amount",
            "global_discount_before_tax", "notes", "total_discount", "total",
            "paid_amount", "outstanding_amount",
            "payments", "lines", "document_pdf_url", "electronic_status",
            "electronic_message", "qr_payload", "failure_code", "failure_message",
        )

    def get_paid_amount(self, obj):
        return str(sum(
            (
                payment.amount_in_sale_currency
                for payment in obj.sales_document.pos_payments.all()
                if payment.status == SalesPayment.Status.REGISTERED
            ),
            Decimal("0.00"),
        ).quantize(Decimal("0.01")))

    def get_cashier_name(self, obj):
        if obj.cashier is None:
            return ""
        return obj.cashier.display_name

    def _company(self, obj):
        store = getattr(obj.sales_document, "store", None)
        return getattr(store, "company", None)

    def get_company_name(self, obj):
        company = self._company(obj)
        return company.name if company else ""

    def get_company_ruc(self, obj):
        company = self._company(obj)
        return company.ruc if company else ""

    def get_company_address(self, obj):
        company = self._company(obj)
        return company.address if company else ""

    def get_company_phone(self, obj):
        company = self._company(obj)
        return company.phone if company else ""

    def get_company_email(self, obj):
        company = self._company(obj)
        return company.email if company else ""

    def get_company_logo_url(self, obj):
        company = self._company(obj)
        if company is None:
            return ""
        try:
            branding = company.branding
        except ObjectDoesNotExist:
            return ""
        return branding.pdf_logo_url or branding.app_logo_url or ""

    def get_store_name(self, obj):
        store = getattr(obj.sales_document, "store", None)
        return store.name if store else ""

    def get_store_address(self, obj):
        store = getattr(obj.sales_document, "store", None)
        return store.address if store else ""

    def get_outstanding_amount(self, obj):
        paid = Decimal(self.get_paid_amount(obj))
        return str(max(
            obj.sales_document.total - paid,
            Decimal("0.00"),
        ).quantize(Decimal("0.01")))

    def get_document_pdf_url(self, obj):
        return reverse("pos:receipt_a4", kwargs={"transaction_id": obj.pk})

    def get_electronic_status(self, obj):
        document = obj.sales_document
        if document.document_type.code not in {"01", "03"}:
            return "NOT_APPLICABLE"
        cdr_status = (document.sunat_cdr_status or "").upper()
        if cdr_status in {"ACCEPTED", "ACEPTADO", "0"}:
            return "ACCEPTED"
        if cdr_status in {"REJECTED", "RECHAZADO"}:
            return "REJECTED"
        if document.sunat_response_code or document.sunat_response_message:
            return "ERROR"
        return "PENDING"

    def get_qr_payload(self, obj):
        document = obj.sales_document
        company = document.store.company if document.store_id else None
        if (
            document.document_type.code not in {"01", "03"}
            or not document.sunat_hash
            or company is None
        ):
            return None
        return "|".join((
            company.ruc,
            document.document_type.code,
            document.series_code,
            document.number,
            str(document.igv_total),
            str(document.total),
            document.issue_date.date().isoformat(),
            document.customer_document_type,
            document.customer_document_number,
            document.sunat_hash,
        ))


class DenominationInputSerializer(serializers.Serializer):
    denomination = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    quantity = serializers.IntegerField(min_value=0)


class CashSessionOpenRequestSerializer(serializers.Serializer):
    register_id = serializers.UUIDField()
    opening_total = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.00"), default=Decimal("0.00")
    )
    denominations = DenominationInputSerializer(many=True, required=False)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)
    currency = serializers.ChoiceField(choices=("PEN", "USD"), default="PEN")


class CashMovementRequestSerializer(serializers.Serializer):
    movement_type = serializers.ChoiceField(choices=("PAY_IN", "PAY_OUT", "WITHDRAWAL", "DEPOSIT"))
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    means_of_payment_id = serializers.UUIDField(required=False, allow_null=True)
    operation_reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    reason_code = serializers.CharField(max_length=40, required=False, allow_blank=True)
    description = serializers.CharField(max_length=500)


class TenderCountInputSerializer(serializers.Serializer):
    means_of_payment_id = serializers.UUIDField()
    counted_amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class CashSessionCloseRequestSerializer(serializers.Serializer):
    counted_cash_total = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.00")
    )
    denominations = DenominationInputSerializer(many=True, required=False)
    next_opening_total = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.00"), default=Decimal("0.00")
    )
    safe_deposit_total = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.00"),
        required=False, allow_null=True,
    )
    bank_deposit_total = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.00"), default=Decimal("0.00")
    )
    bank_deposit_destination = serializers.CharField(
        max_length=200, required=False, allow_blank=True
    )
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)
    tender_counts = TenderCountInputSerializer(many=True, required=False)


class CreditCollectionRequestSerializer(serializers.Serializer):
    sales_document_id = serializers.UUIDField()
    cash_session_id = serializers.UUIDField()
    means_of_payment_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    received_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.00"), required=False
    )
    operation_reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    idempotency_key = serializers.UUIDField()


class PosSaleLineInputSerializer(serializers.Serializer):
    product_id = serializers.UUIDField(required=False, allow_null=True)
    line_type = serializers.ChoiceField(choices=("PRODUCT", "MANUAL"), default="PRODUCT")
    unit_id = serializers.UUIDField(required=False, allow_null=True)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0.001"))
    unit_price = serializers.DecimalField(
        max_digits=14, decimal_places=6, min_value=Decimal("0.00"), required=False
    )
    discount_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.00"), default=Decimal("0.00")
    )
    tax_type = serializers.ChoiceField(
        choices=("10", "11", "20", "30", "40"), default="10"
    )
    igv_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0.00"), default=Decimal("0.00")
    )
    sunat_product_code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    product_code = serializers.CharField(max_length=100, required=False, allow_blank=True)
    memo = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["line_type"] == "PRODUCT" and not attrs.get("product_id"):
            raise serializers.ValidationError({"product_id": "Seleccione un producto."})
        if attrs["line_type"] == "MANUAL":
            if not (attrs.get("description") or "").strip():
                raise serializers.ValidationError({"description": "Ingrese una descripción."})
            if not attrs.get("unit_id"):
                raise serializers.ValidationError({"unit_id": "Seleccione una unidad."})
            if "unit_price" not in attrs:
                raise serializers.ValidationError({"unit_price": "Ingrese el precio de venta."})
        return attrs


class PosPaymentInputSerializer(serializers.Serializer):
    means_of_payment_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    currency = serializers.ChoiceField(choices=("PEN", "USD"), required=False)
    exchange_rate = serializers.DecimalField(
        max_digits=10, decimal_places=6, min_value=Decimal("0.000001"), required=False
    )
    amount_in_sale_currency = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.01"), required=False
    )
    received_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.00"), required=False
    )
    change_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.00"), required=False
    )
    operation_reference = serializers.CharField(max_length=120, required=False, allow_blank=True)


class PosCheckoutRequestSerializer(serializers.Serializer):
    register_id = serializers.UUIDField()
    cash_session_id = serializers.UUIDField()
    idempotency_key = serializers.UUIDField()
    document_type = serializers.ChoiceField(choices=("NV", "01", "03"), default="NV")
    series_id = serializers.UUIDField()
    customer_id = serializers.UUIDField(required=False, allow_null=True)
    payment_condition = serializers.ChoiceField(choices=("CASH", "CREDIT"), default="CASH")
    payment_method_id = serializers.UUIDField(required=False, allow_null=True)
    due_date = serializers.DateField(required=False, allow_null=True)
    warehouse_id = serializers.UUIDField(required=False, allow_null=True)
    price_list_id = serializers.UUIDField(required=False, allow_null=True)
    currency = serializers.ChoiceField(choices=("PEN", "USD"), default="PEN")
    exchange_rate = serializers.DecimalField(
        max_digits=10, decimal_places=6, min_value=Decimal("0.000001"), default=Decimal("1")
    )
    global_discount_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.00"), default=Decimal("0.00")
    )
    global_discount_before_tax = serializers.BooleanField(default=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    device_identifier = serializers.CharField(max_length=120, required=False, allow_blank=True)
    lines = PosSaleLineInputSerializer(many=True, allow_empty=False)
    payments = PosPaymentInputSerializer(many=True, allow_empty=True, required=False, default=list)


class InvoiceTicketRequestSerializer(serializers.Serializer):
    source_document_ids = serializers.ListField(
        child=serializers.UUIDField(), allow_empty=False
    )


class ConsolidatedInvoiceRequestSerializer(InvoiceTicketRequestSerializer):
    invoice_series_id = serializers.UUIDField()


class PosCustomerCreateRequestSerializer(serializers.Serializer):
    document_type = serializers.ChoiceField(choices=("0", "1", "4", "6", "7", "A"))
    document_number = serializers.CharField(max_length=20)
    legal_name = serializers.CharField(max_length=300)
    trade_name = serializers.CharField(max_length=300, required=False, allow_blank=True)
    address = serializers.CharField(max_length=500, required=False, allow_blank=True)
    ubigeo = serializers.CharField(max_length=6, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    email = serializers.EmailField(max_length=200, required=False, allow_blank=True)

    def validate(self, attrs):
        number = attrs["document_number"].strip()
        if attrs["document_type"] == "6" and (len(number) != 11 or not number.isdigit()):
            raise serializers.ValidationError({"document_number": "El RUC debe tener 11 digitos."})
        attrs["document_number"] = number
        attrs["legal_name"] = attrs["legal_name"].strip()
        return attrs


class PosProductCreateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=500, trim_whitespace=True)
    sku = serializers.CharField(max_length=100, trim_whitespace=True)
    barcode = serializers.CharField(max_length=100, required=False, allow_blank=True)
    unit_id = serializers.UUIDField()
    category_id = serializers.UUIDField(required=False, allow_null=True)
    sale_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.00")
    )
    includes_tax = serializers.BooleanField(default=True)
    tax_type = serializers.ChoiceField(choices=("10", "20", "30", "40"), default="10")
    tracks_inventory = serializers.BooleanField(default=True)

    def validate(self, attrs):
        attrs["name"] = attrs["name"].strip()
        attrs["sku"] = attrs["sku"].strip().upper()
        attrs["barcode"] = attrs.get("barcode", "").strip()
        if not attrs["name"]:
            raise serializers.ValidationError({"name": "Ingrese el nombre del producto."})
        if not attrs["sku"]:
            raise serializers.ValidationError({"sku": "Ingrese el código del producto."})
        return attrs


class PosVoidRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, allow_blank=False, trim_whitespace=True)


class PosReprintRequestSerializer(serializers.Serializer):
    width = serializers.ChoiceField(choices=("58", "80"), default="80")


class PosReturnLineInputSerializer(serializers.Serializer):
    line_id = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=4, min_value=Decimal("0.0001"))


class PosReturnRequestSerializer(serializers.Serializer):
    cash_session_id = serializers.UUIDField()
    idempotency_key = serializers.UUIDField()
    credit_note_series_id = serializers.UUIDField(required=False, allow_null=True)
    reason_code = serializers.CharField(max_length=5, default="01")
    reason = serializers.CharField(max_length=500, allow_blank=False, trim_whitespace=True)
    refund_means_of_payment_id = serializers.UUIDField()
    operation_reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    lines = PosReturnLineInputSerializer(many=True, allow_empty=False)


class PosDebitNoteLineInputSerializer(serializers.Serializer):
    line_id = serializers.UUIDField()
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=4, min_value=Decimal("0.0001"))
    unit_price = serializers.DecimalField(max_digits=14, decimal_places=6, min_value=Decimal("0.000001"))


class PosDebitNoteRequestSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    series_id = serializers.UUIDField()
    reason_code = serializers.CharField(max_length=5)
    reason = serializers.CharField(max_length=500, allow_blank=False, trim_whitespace=True)
    lines = PosDebitNoteLineInputSerializer(many=True, allow_empty=False)


class PosReturnSerializer(serializers.ModelSerializer):
    credit_note_id = serializers.UUIDField(read_only=True, allow_null=True)
    credit_note_series = serializers.CharField(source="credit_note.series_code", read_only=True, allow_null=True)
    credit_note_number = serializers.CharField(source="credit_note.number", read_only=True, allow_null=True)
    refund_method = serializers.SerializerMethodField()

    class Meta:
        model = PosReturn
        fields = (
            "id", "status", "original_transaction", "credit_note_id",
            "credit_note_series", "credit_note_number", "currency", "total",
            "reason_code", "reason", "refund_method", "completed_at",
        )

    def get_refund_method(self, obj):
        payment = obj.refund_payments.first()
        return payment.means_of_payment.name if payment else None
