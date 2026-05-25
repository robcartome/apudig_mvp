import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


# ── Maestros ──────────────────────────────────────────────────────────────────

class Category(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE,
        related_name="categories", null=True, blank=True,
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "categories"
        ordering = ["name"]
        unique_together = (("company", "code"),)

    def __str__(self) -> str:
        return self.name


class Brand(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE,
        related_name="brands", null=True, blank=True,
    )
    name = models.CharField(max_length=255)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "brands"
        ordering = ["name"]
        unique_together = (("company", "name"),)

    def __str__(self) -> str:
        return self.name


class Unit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)

    class Meta:
        db_table = "units"
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class PriceList(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE,
        related_name="price_lists", null=True, blank=True,
    )
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=500, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "price_lists"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Product(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE,
        related_name="products", null=True, blank=True,
    )
    name = models.CharField(max_length=500)
    sku = models.CharField(max_length=100)
    barcode = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=1000, blank=True)
    model = models.CharField(max_length=200, blank=True)
    image = models.CharField(max_length=500, blank=True)
    price_purchase = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_sale = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="products")
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "products"
        ordering = ["name"]
        unique_together = (("company", "sku"),)

    def __str__(self) -> str:
        return f"[{self.sku}] {self.name}"


class ProductPrice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="prices")
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name="product_prices")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="PEN")
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "product_prices"
        unique_together = ("product", "price_list")


# ── Operativo ─────────────────────────────────────────────────────────────────

class Warehouse(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey("companies.Store", on_delete=models.CASCADE, related_name="warehouses")
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=500, blank=True)
    active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "warehouses"
        ordering = ["store_id", "name"]

    def __str__(self) -> str:
        return f"{self.store} / {self.name}"


class WarehouseLocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="locations")
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=500, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "warehouse_locations"
        ordering = ["warehouse", "code"]
        unique_together = ("warehouse", "code")

    def __str__(self) -> str:
        return f"{self.warehouse.name} / {self.code} - {self.name}"


class StockByWarehouse(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="stocks")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="stocks")
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    location = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "stock_by_warehouse"
        unique_together = ("product", "warehouse")

    def __str__(self) -> str:
        return f"{self.product.sku} @ {self.warehouse}: {self.quantity}"


class StoreProductConfig(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey("companies.Store", on_delete=models.CASCADE, related_name="product_configs")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="store_configs")
    min_stock = models.IntegerField(default=0)
    max_stock = models.IntegerField(default=0)

    class Meta:
        db_table = "store_product_configs"
        unique_together = ("store", "product")


class MovementType(models.TextChoices):
    ENTRY = "ENTRY", "Entrada"
    EXIT = "EXIT", "Salida"
    TRANSFER = "TRANSFER", "Transferencia"
    ADJUSTMENT = "ADJUSTMENT", "Ajuste"


class MovementStatus(models.TextChoices):
    DRAFT = "DRAFT", "Borrador"
    CONFIRMED = "CONFIRMED", "Confirmado"
    CLOSED = "CLOSED", "Cerrado"


class Movement(TimeStampedModel):
    MOVEMENT_TYPES = MovementType.choices
    STATUS_CHOICES = MovementStatus.choices

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    store = models.ForeignKey(
        "companies.Store", on_delete=models.SET_NULL, null=True, blank=True, related_name="movements"
    )
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.SET_NULL, null=True, blank=True, related_name="movements"
    )
    warehouse_origin = models.ForeignKey(
        Warehouse, on_delete=models.SET_NULL, null=True, blank=True, related_name="transfers_out"
    )
    warehouse_dest = models.ForeignKey(
        Warehouse, on_delete=models.SET_NULL, null=True, blank=True, related_name="transfers_in"
    )
    date = models.DateTimeField()
    reason = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    series = models.CharField(max_length=10, blank=True)
    number = models.CharField(max_length=20, blank=True)
    reference_doc = models.CharField(max_length=100, blank=True)
    supplier = models.ForeignKey(
        "partners.Supplier", on_delete=models.SET_NULL, null=True, blank=True, related_name="movements"
    )
    customer = models.ForeignKey(
        "partners.CoreCustomer", on_delete=models.SET_NULL, null=True, blank=True, related_name="movements"
    )
    carrier = models.ForeignKey(
        "partners.Carrier", on_delete=models.SET_NULL, null=True, blank=True, related_name="movements"
    )
    document_type = models.ForeignKey(
        "partners.DocumentType", on_delete=models.SET_NULL, null=True, blank=True, related_name="movements"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="movements"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=MovementStatus.DRAFT)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_movements",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_movements",
    )

    class Meta:
        db_table = "movements"
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.type} {self.number} ({self.date:%Y-%m-%d})"

    @property
    def lock_mode_enabled(self) -> bool:
        if not self.store_id:
            return True
        if hasattr(self, "store") and self.store:
            return bool(getattr(self.store, "lock_movement_edits", True))
        return True

    @property
    def has_posterior_related_movements(self) -> bool:
        """Determina si existen movimientos posteriores relacionados."""
        if hasattr(self, "_has_posterior_related_movements_cache"):
            return self._has_posterior_related_movements_cache

        product_ids = list(self.details.values_list("product_id", flat=True))
        if not product_ids:
            self._has_posterior_related_movements_cache = False
            return self._has_posterior_related_movements_cache

        warehouse_ids = {
            self.warehouse_id,
            self.warehouse_origin_id,
            self.warehouse_dest_id,
        }
        warehouse_ids.discard(None)
        if not warehouse_ids:
            self._has_posterior_related_movements_cache = False
            return self._has_posterior_related_movements_cache

        date_q = Q(date__gt=self.date)
        if self.created_at:
            date_q |= Q(date=self.date, created_at__gt=self.created_at)

        self._has_posterior_related_movements_cache = (
            Movement.objects
            .exclude(pk=self.pk)
            .filter(store_id=self.store_id)
            .filter(details__product_id__in=product_ids)
            .filter(date_q)
            .filter(
                Q(warehouse_id__in=warehouse_ids)
                | Q(warehouse_origin_id__in=warehouse_ids)
                | Q(warehouse_dest_id__in=warehouse_ids)
            )
            .distinct()
            .exists()
        )
        return self._has_posterior_related_movements_cache

    @property
    def lock_reason(self) -> str:
        if self.status == MovementStatus.CLOSED:
            return "Movimiento cerrado. Solo se permite corrección con nuevo movimiento."
        if self.status == MovementStatus.CONFIRMED:
            return "Movimiento confirmado. Para cambiarlo debe registrar un movimiento correctivo."
        if self.lock_mode_enabled and self.has_posterior_related_movements:
            return "No editable: existen movimientos posteriores relacionados en el mismo producto/almacén."
        return ""

    @property
    def is_locked_for_changes(self) -> bool:
        if self.status in (MovementStatus.CONFIRMED, MovementStatus.CLOSED):
            return True
        if not self.lock_mode_enabled:
            return False
        return self.has_posterior_related_movements


class MovementDetail(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    movement = models.ForeignKey(Movement, on_delete=models.CASCADE, related_name="details")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="movement_details")
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit_price = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    physical_quantity = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    location = models.ForeignKey(
        WarehouseLocation, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="movement_details"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "movement_details"

    def __str__(self) -> str:
        return f"{self.product.sku} x{self.quantity}"

    @property
    def system_quantity(self):
        """Cantidad del sistema justo antes del ajuste (solo para ADJUSTMENT)."""
        if self.physical_quantity is None:
            return None
        return Decimal(str(self.physical_quantity)) - Decimal(str(self.quantity))


class MovementAuditLog(models.Model):
    class ActionType(models.TextChoices):
        CREATE = "CREATE", "Creación"
        UPDATE = "UPDATE", "Actualización"
        CONFIRM = "CONFIRM", "Confirmación"
        CLOSE = "CLOSE", "Cierre"
        DELETE = "DELETE", "Eliminación"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    movement = models.ForeignKey(Movement, on_delete=models.CASCADE, related_name="audit_logs")
    action = models.CharField(max_length=20, choices=ActionType.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movement_audit_logs",
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    before_data = models.JSONField(null=True, blank=True)
    after_data = models.JSONField(null=True, blank=True)
    message = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "movement_audit_logs"
        ordering = ["-changed_at"]
