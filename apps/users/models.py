import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email: str, password: str | None = None, **extra):
        if not email:
            raise ValueError("El email es obligatorio")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, max_length=255)
    name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        db_table = "users"
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self) -> str:
        return self.email

    @property
    def display_name(self) -> str:
        return self.name or self.email


class Role(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        db_table = "roles"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Permission(models.Model):
    """
    Permiso granular con estructura acción + módulo.

    Ejemplo:
        action_name = "read"
        module      = "inventory.products"
        code        = "read.inventory.products"  (autogenerado)
        description = "Leer productos del inventario"
    """
    ACTION_READ = "read"
    ACTION_MANAGE = "manage"
    ACTION_AUTHORIZE = "authorize"
    ACTION_CHOICES = [
        (ACTION_READ, "Leer"),
        (ACTION_MANAGE, "Gestionar"),
        (ACTION_AUTHORIZE, "Autorizar"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=120, unique=True)
    action_name = models.CharField(max_length=30, choices=ACTION_CHOICES, blank=True)
    module = models.CharField(max_length=100, blank=True, help_text="Ej: inventory.products")
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "permissions"
        ordering = ["module", "action_name"]

    def __str__(self) -> str:
        return self.display_label

    @property
    def display_label(self) -> str:
        """Returns 'Gestionar - Inventario/Productos' style label."""
        if self.action_name and self.module:
            action_display = dict(self.ACTION_CHOICES).get(self.action_name, self.action_name.capitalize())
            module_display = self.module.replace(".", "/").replace("_", " ").title()
            return f"{action_display} - {module_display}"
        return self.description or self.code

    def save(self, *args, **kwargs):
        # Auto-generate code from action_name + module if both set
        if self.action_name and self.module and not self.code:
            self.code = f"{self.action_name}.{self.module}"
        super().save(*args, **kwargs)


class RolePermission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="role_permissions")

    class Meta:
        db_table = "role_permissions"
        unique_together = ("role", "permission")


class UserRole(models.Model):
    """Asignación de roles a usuarios por empresa (multitenancy)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="user_roles")
    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="user_roles")
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        db_table = "user_roles"
        unique_together = ("user", "role", "company")


class UserOperationalFlags(models.Model):
    """
    Flags operativos por usuario por empresa.
    Permiten configurar permisos especiales sin crear un rol completo.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="operational_flags")
    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="user_operational_flags")

    # Configuración general
    is_operation_admin = models.BooleanField(default=False, verbose_name="Administrador Módulo Operaciones")
    ignore_notification_emails = models.BooleanField(default=False, verbose_name="No recibir notificaciones por correo")

    # Permisos de administración
    is_seller_profile = models.BooleanField(default=False, verbose_name="Perfil Vendedor")
    restricted_shop_access = models.BooleanField(default=False, verbose_name="Acceso Restringido Compras")
    can_authorize_purchase_request = models.BooleanField(default=False, verbose_name="Autorizar cambio estados SC")
    can_close_purchase_order = models.BooleanField(default=False, verbose_name="Activar para cerrar OC")
    restrict_unaccepted_po_pdf = models.BooleanField(default=False, verbose_name="Restringir PDF de OC sin aceptar")
    can_close_sale_order = models.BooleanField(default=False, verbose_name="Activar para cerrar OV")
    see_all_price_lists = models.BooleanField(default=False, verbose_name="Ver todas las listas de precio en ventas")
    can_close_credits = models.BooleanField(default=False, verbose_name="Activar para cerrar Créditos")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_operational_flags"
        unique_together = ("user", "company")
        verbose_name = "Flags Operativos de Usuario"
        verbose_name_plural = "Flags Operativos de Usuarios"

    def __str__(self) -> str:
        return f"Flags de {self.user} en {self.company}"


class UserStore(models.Model):
    ROLE_CHOICES = [("ADMIN", "Admin"), ("SELLER", "Vendedor"), ("CASHIER", "Cajero")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_stores")
    store = models.ForeignKey("companies.Store", on_delete=models.CASCADE, related_name="user_stores")
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default="SELLER")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_stores"
        unique_together = ("user", "store")


class Employee(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="employees")
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="employee")
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    document_type = models.CharField(max_length=10)
    document_number = models.CharField(max_length=20)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "employees"

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
