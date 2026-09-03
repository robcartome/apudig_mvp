import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.managers import CompanyScopedManager
from apps.core.models import TimeStampedModel


# ── Maestros ──────────────────────────────────────────────────────────────────

class Category(TimeStampedModel):
    objects = CompanyScopedManager()
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
    objects = CompanyScopedManager()
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
    objects = CompanyScopedManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE,
        related_name="price_lists", null=True, blank=True,
    )
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=500, blank=True)
    active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False, verbose_name="Lista por defecto")

    class Meta:
        db_table = "price_lists"
        ordering = ["-is_default", "name"]

    def __str__(self) -> str:
        return self.name


class Product(TimeStampedModel):
    objects = CompanyScopedManager()
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
    image_key = models.CharField(max_length=500, blank=True)
    secondary_image_key = models.CharField(max_length=500, blank=True)
    tertiary_image_key = models.CharField(max_length=500, blank=True)
    price_purchase = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_sale = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="products")
    active = models.BooleanField(default=True)
    tracks_inventory = models.BooleanField(
        default=True,
        help_text="Desmarcar para servicios u otros conceptos que no modifican stock.",
    )

    class Meta:
        db_table = "products"
        ordering = ["name"]
        unique_together = (("company", "sku"),)

    def __str__(self) -> str:
        return f"[{self.sku}] {self.name}"

    @property
    def image(self) -> str:
        from apps.inventory.product_image_storage import build_public_url

        return build_public_url(self.image_key)

    @property
    def secondary_image(self) -> str:
        from apps.inventory.product_image_storage import build_public_url

        return build_public_url(self.secondary_image_key)

    @property
    def tertiary_image(self) -> str:
        from apps.inventory.product_image_storage import build_public_url

        return build_public_url(self.tertiary_image_key)

    @property
    def image_urls(self) -> list[str]:
        from apps.inventory.product_image_storage import build_public_url

        return [
            url
            for url in (
                build_public_url(self.image_key),
                build_public_url(self.secondary_image_key),
                build_public_url(self.tertiary_image_key),
            )
            if url
        ]


class ProductSupplier(TimeStampedModel):
    """Commercial identification of a product in a supplier's catalog."""

    objects = CompanyScopedManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE, related_name="product_suppliers"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="supplier_relations"
    )
    supplier = models.ForeignKey(
        "partners.Supplier", on_delete=models.CASCADE, related_name="product_relations"
    )
    supplier_code = models.CharField(max_length=100, blank=True)
    supplier_product_name = models.CharField(max_length=500, blank=True)
    supplier_description = models.TextField(blank=True)
    purchase_price = models.DecimalField(max_digits=14, decimal_places=6, null=True, blank=True)
    is_preferred = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "product_suppliers"
        ordering = ["-is_preferred", "supplier__name"]
        constraints = [
            models.UniqueConstraint(
                fields=("product", "supplier"), name="uniq_product_supplier"
            ),
            models.UniqueConstraint(
                fields=("company", "supplier", "supplier_code"),
                condition=~Q(supplier_code=""),
                name="uniq_supplier_product_code_nonempty",
            ),
            models.UniqueConstraint(
                fields=("product",),
                condition=Q(is_preferred=True),
                name="uniq_preferred_supplier_per_product",
            ),
            models.CheckConstraint(
                condition=Q(active=True) | Q(is_preferred=False),
                name="product_supplier_preferred_requires_active",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}
        if self.product_id and self.company_id != self.product.company_id:
            errors["product"] = "El producto debe pertenecer a la empresa de la relación."
        if self.supplier_id and self.company_id != self.supplier.company_id:
            errors["supplier"] = "El proveedor debe pertenecer a la empresa del producto."
        if self.is_preferred and not self.active:
            errors["is_preferred"] = "Un proveedor preferido debe estar activo."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.product_id:
            self.company_id = self.product.company_id
        self.supplier_code = (self.supplier_code or "").strip()
        self.supplier_product_name = (self.supplier_product_name or "").strip()
        self.clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        code = f" [{self.supplier_code}]" if self.supplier_code else ""
        return f"{self.product} / {self.supplier}{code}"


class ProductUnit(models.Model):
    """Unidad/presentación habilitada para un producto y su equivalencia en stock."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="unit_conversions")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="product_conversions")
    conversion_factor = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    sale_price = models.DecimalField(max_digits=14, decimal_places=6, null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=14, decimal_places=6, null=True, blank=True)
    is_default_sale = models.BooleanField(default=False)
    is_default_purchase = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "product_units"
        ordering = ["unit__code"]
        constraints = [
            models.UniqueConstraint(fields=("product", "unit"), name="uniq_product_unit"),
            models.CheckConstraint(
                condition=models.Q(conversion_factor__gt=0), name="product_unit_factor_gt_zero"
            ),
            models.UniqueConstraint(
                condition=models.Q(is_default_sale=True),
                fields=("product",),
                name="uniq_product_default_sale_unit",
            ),
            models.UniqueConstraint(
                condition=models.Q(is_default_purchase=True),
                fields=("product",),
                name="uniq_product_default_purchase_unit",
            ),
        ]

    def __str__(self):
        return f"{self.product} / {self.unit.code} × {self.conversion_factor}"


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
    objects = CompanyScopedManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey("companies.Store", on_delete=models.CASCADE, related_name="warehouses")
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=500, blank=True)
    active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    allow_negative_stock = models.BooleanField(default=False)

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


class MovementOrigin(models.TextChoices):
    MANUAL = "MANUAL", "Manual"
    SALE = "SALE", "Venta"
    SALE_REVERSAL = "SALE_REVERSAL", "Reversión de venta"
    PURCHASE = "PURCHASE", "Compra"
    PURCHASE_REVERSAL = "PURCHASE_REVERSAL", "Reversión de compra"


class Movement(TimeStampedModel):
    objects = CompanyScopedManager()
    MOVEMENT_TYPES = MovementType.choices
    STATUS_CHOICES = MovementStatus.choices
    ORIGIN_CHOICES = MovementOrigin.choices

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    origin = models.CharField(
        max_length=30,
        choices=ORIGIN_CHOICES,
        default=MovementOrigin.MANUAL,
    )
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
    reversal_of = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reversal",
    )
    supplier = models.ForeignKey(
        "partners.Supplier", on_delete=models.SET_NULL, null=True, blank=True, related_name="movements"
    )
    customer = models.ForeignKey(
        "partners.Customer", on_delete=models.SET_NULL, null=True, blank=True, related_name="movements"
    )
    carrier = models.ForeignKey(
        "partners.Carrier", on_delete=models.SET_NULL, null=True, blank=True, related_name="movements"
    )
    document_type = models.ForeignKey(
        "partners.DocumentType", on_delete=models.SET_NULL, null=True, blank=True, related_name="movements"
    )
    purchase_document = models.ForeignKey(
        "purchases.PurchaseDocument",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_movements",
    )
    purchase_receipt = models.ForeignKey(
        "purchases.PurchaseReceipt",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_movements",
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
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="movement_details")
    unit_code = models.CharField(max_length=10, default="NIU")
    conversion_factor = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    stock_quantity = models.DecimalField(max_digits=18, decimal_places=6, default=0)
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
