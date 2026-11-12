import re
import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from apps.core.models import TimeStampedModel


_HOST_LABEL_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_HEX_COLOR_VALIDATOR = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="Use un color hexadecimal de seis dÃ­gitos, por ejemplo #0B1F3A.",
)


def normalize_hostname(value: str) -> str:
    """Return a canonical ASCII hostname or raise a validation error."""
    raw = (value or "").strip().lower().rstrip(".")
    if not raw or "://" in raw or "/" in raw or ":" in raw:
        raise ValidationError("Ingrese un hostname válido sin protocolo, puerto ni ruta.")

    try:
        hostname = raw.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValidationError("El hostname no es válido.") from exc

    if len(hostname) > 253:
        raise ValidationError("El hostname supera la longitud permitida.")
    if hostname.replace(".", "").isdigit():
        raise ValidationError("No se permiten direcciones IP como dominio de tienda.")
    if any(not _HOST_LABEL_RE.fullmatch(label) for label in hostname.split(".")):
        raise ValidationError("El hostname contiene etiquetas no válidas.")
    return hostname


def is_reserved_hostname(hostname: str) -> bool:
    """Return whether a hostname belongs to the reserved APUDIG surface."""
    normalized = normalize_hostname(hostname)
    platform_domain = getattr(settings, "WEBSITE_PLATFORM_DOMAIN", "apudig.com").lower().strip(".")
    reserved_labels = getattr(
        settings,
        "WEBSITE_RESERVED_SUBDOMAINS",
        ("www", "web", "admin", "api", "media", "status"),
    )
    return normalized == platform_domain or normalized in {
        f"{label.lower().strip()}.{platform_domain}"
        for label in reserved_labels
        if label.strip()
    }


class Website(TimeStampedModel):
    """Minimal storefront identity used to scope the public catalog."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Borrador"
        PUBLISHED = "PUBLISHED", "Publicado"
        SUSPENDED = "SUSPENDED", "Suspendido"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.OneToOneField(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="website",
    )
    name = models.CharField(max_length=255)
    template_key = models.CharField(max_length=64, default="ecommerce")
    template_schema_version = models.PositiveSmallIntegerField(default=1)
    slug = models.SlugField(max_length=140, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    default_locale = models.CharField(max_length=15, default="es-PE")
    timezone = models.CharField(max_length=64, default="America/Lima")
    currency = models.CharField(max_length=3, default="PEN")
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="websites_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="websites_updated",
    )

    class Meta:
        db_table = "websites"
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=("slug",),
                condition=~models.Q(slug=""),
                name="uniq_nonempty_website_slug",
            ),
        ]

    def clean(self):
        super().clean()
        if self.template_key != "ecommerce" or self.template_schema_version != 1:
            raise ValidationError({"template_key": "La plantilla o versión no está registrada."})

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:100] or "website"
            self.slug = f"{base}-{str(self.company_id)[:8]}"
        self.currency = (self.currency or "PEN").upper()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class WebsiteDomain(TimeStampedModel):
    """Verified hostname allowed to resolve one public website."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        VERIFYING = "VERIFYING", "Verificando"
        VERIFIED = "VERIFIED", "Verificado"
        ACTIVE = "ACTIVE", "Activo"
        FAILED = "FAILED", "Fallido"
        DISABLED = "DISABLED", "Deshabilitado"

    class Kind(models.TextChoices):
        SUBDOMAIN = "SUBDOMAIN", "Subdominio APUDIG"
        CUSTOM = "CUSTOM", "Dominio personalizado"
        ALIAS = "ALIAS", "Alias"

    class VerificationMethod(models.TextChoices):
        DNS_TXT = "DNS_TXT", "Registro DNS TXT"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    website = models.ForeignKey(
        Website,
        on_delete=models.CASCADE,
        related_name="domains",
    )
    hostname = models.CharField(max_length=253, unique=True)
    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        default=Kind.SUBDOMAIN,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    is_primary = models.BooleanField(default=False)
    verification_method = models.CharField(
        max_length=20,
        choices=VerificationMethod.choices,
        default=VerificationMethod.DNS_TXT,
    )
    verification_token_hash = models.CharField(max_length=128, blank=True, editable=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    last_verification_error = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = "website_domains"
        ordering = ("hostname",)
        constraints = [
            models.UniqueConstraint(
                fields=("website",),
                condition=models.Q(is_primary=True),
                name="uniq_primary_domain_per_website",
            ),
        ]

    def clean(self):
        super().clean()
        self.hostname = normalize_hostname(self.hostname)
        if is_reserved_hostname(self.hostname):
            raise ValidationError({"hostname": "Este hostname estÃ¡ reservado por APUDIG."})
        if self.status == self.Status.ACTIVE and not self.verified_at:
            raise ValidationError({"status": "Un dominio activo debe estar verificado."})
        if self.is_primary and self.status != self.Status.ACTIVE:
            raise ValidationError({"is_primary": "Solo un dominio activo puede ser primario."})

    def save(self, *args, **kwargs):
        self.hostname = normalize_hostname(self.hostname)
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.hostname


class WebsiteSettings(TimeStampedModel):
    """Public identity and contact settings for one website."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    website = models.OneToOneField(
        Website,
        on_delete=models.CASCADE,
        related_name="settings",
    )
    business_name = models.CharField(max_length=255, blank=True)
    logo_url = models.URLField(max_length=1000, blank=True)
    favicon_url = models.URLField(max_length=1000, blank=True)
    primary_color = models.CharField(
        max_length=7,
        default="#0B1F3A",
        validators=[_HEX_COLOR_VALIDATOR],
    )
    accent_color = models.CharField(
        max_length=7,
        default="#F97316",
        validators=[_HEX_COLOR_VALIDATOR],
    )
    background_color = models.CharField(
        max_length=7,
        default="#FFFFFF",
        validators=[_HEX_COLOR_VALIDATOR],
    )
    text_color = models.CharField(
        max_length=7,
        default="#111827",
        validators=[_HEX_COLOR_VALIDATOR],
    )
    whatsapp = models.CharField(max_length=30, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=500, blank=True)
    business_hours = models.JSONField(default=dict, blank=True)
    social_links = models.JSONField(default=dict, blank=True)
    default_seo_title = models.CharField(max_length=70, blank=True)
    default_seo_description = models.CharField(max_length=170, blank=True)
    heading_font = models.CharField(max_length=30, default="system")
    body_font = models.CharField(max_length=30, default="system")
    border_radius = models.PositiveSmallIntegerField(default=8)
    footer_text = models.CharField(max_length=300, blank=True)
    google_maps_url = models.URLField(max_length=1000, blank=True)
    default_noindex = models.BooleanField(default=False)
    logo_media = models.ForeignKey(
        "websites.WebsiteMedia", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="logo_for_settings",
    )
    favicon_media = models.ForeignKey(
        "websites.WebsiteMedia", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="favicon_for_settings",
    )

    class Meta:
        db_table = "website_settings"

    def clean(self):
        super().clean()
        allowed_social_keys = {"facebook", "instagram", "youtube", "tiktok", "linkedin"}
        unknown_keys = set(self.social_links or {}) - allowed_social_keys
        if unknown_keys:
            raise ValidationError({
                "social_links": f"Redes no permitidas: {', '.join(sorted(unknown_keys))}."
            })
        allowed_fonts = {"system", "inter", "serif"}
        if self.heading_font not in allowed_fonts or self.body_font not in allowed_fonts:
            raise ValidationError("La tipografía seleccionada no está permitida.")
        if self.border_radius > 32:
            raise ValidationError({"border_radius": "El radio debe estar entre 0 y 32 píxeles."})
        for field in ("logo_media", "favicon_media"):
            media = getattr(self, field, None)
            if media and media.website_id != self.website_id:
                raise ValidationError({field: "El medio debe pertenecer al mismo sitio web."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


    def __str__(self):
        return f"Configuración de {self.website}"


class WebsitePage(TimeStampedModel):
    """Editable page whose public representation is an immutable revision."""

    class PageType(models.TextChoices):
        HOME = "HOME", "Inicio"
        STANDARD = "STANDARD", "Estándar"
        CONTACT = "CONTACT", "Contacto"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Borrador"
        PUBLISHED = "PUBLISHED", "Publicado"
        ARCHIVED = "ARCHIVED", "Archivado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name="pages")
    slug = models.SlugField(max_length=140)
    title = models.CharField(max_length=160)
    page_type = models.CharField(max_length=20, choices=PageType.choices, default=PageType.STANDARD)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    seo_title = models.CharField(max_length=70, blank=True)
    seo_description = models.CharField(max_length=170, blank=True)
    og_image_url = models.URLField(max_length=1000, blank=True)
    noindex = models.BooleanField(default=False)
    draft_version = models.PositiveIntegerField(default=1)
    published_version = models.PositiveIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="website_pages_created")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="website_pages_updated")

    class Meta:
        db_table = "website_pages"
        ordering = ("page_type", "title")
        constraints = [
            models.UniqueConstraint(fields=("website", "slug"), name="uniq_page_slug_per_website"),
            models.UniqueConstraint(fields=("website",), condition=models.Q(page_type="HOME"), name="uniq_home_page_per_website"),
        ]

    def clean(self):
        super().clean()
        if self.page_type == self.PageType.HOME and self.slug != "home":
            raise ValidationError({"slug": "La página de inicio debe usar el slug 'home'."})

    def save(self, *args, **kwargs):
        self.slug = "home" if self.page_type == self.PageType.HOME else slugify(self.slug)
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.website}: {self.title}"


class WebsiteSection(TimeStampedModel):
    """A validated, ordered block in the editable page draft."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    page = models.ForeignKey(WebsitePage, on_delete=models.CASCADE, related_name="sections")
    section_type = models.CharField(max_length=60)
    schema_version = models.PositiveSmallIntegerField(default=1)
    position = models.PositiveIntegerField()
    enabled = models.BooleanField(default=True)
    config = models.JSONField(default=dict)

    class Meta:
        db_table = "website_sections"
        ordering = ("position",)
        constraints = [models.UniqueConstraint(fields=("page", "position"), name="uniq_section_position_per_page")]

    def clean(self):
        super().clean()
        from apps.websites.blocks import validate_block_config
        self.config = validate_block_config(self.section_type, self.schema_version, self.config)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.page} / {self.section_type} ({self.position})"


class WebsitePageRevision(models.Model):
    """Immutable public snapshot created by a publish operation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    page = models.ForeignKey(WebsitePage, on_delete=models.CASCADE, related_name="revisions")
    version = models.PositiveIntegerField()
    snapshot = models.JSONField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="website_page_revisions_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "website_page_revisions"
        ordering = ("-version",)
        constraints = [models.UniqueConstraint(fields=("page", "version"), name="uniq_revision_version_per_page")]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Las revisiones publicadas son inmutables.")
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.page} v{self.version}"


class WebsiteMedia(TimeStampedModel):
    """Website-owned image stored in R2 and retained for published snapshots."""

    class Kind(models.TextChoices):
        IMAGE = "IMAGE", "Imagen"
        LOGO = "LOGO", "Logo"
        FAVICON = "FAVICON", "Favicon"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name="media")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.IMAGE)
    storage_key = models.CharField(max_length=500)
    thumbnail_key = models.CharField(max_length=500, blank=True)
    original_name = models.CharField(max_length=255)
    alt_text = models.CharField(max_length=180, blank=True)
    mime_type = models.CharField(max_length=100, default="image/webp")
    size = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    checksum = models.CharField(max_length=64)
    is_deleted = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="website_media_created",
    )

    class Meta:
        db_table = "website_media"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("website", "checksum"), condition=models.Q(is_deleted=False),
                name="uniq_active_media_checksum_per_website",
            )
        ]

    @property
    def url(self):
        from apps.inventory.product_image_storage import build_public_url
        return build_public_url(self.storage_key)

    @property
    def thumbnail_url(self):
        from apps.inventory.product_image_storage import build_public_url
        return build_public_url(self.thumbnail_key) or self.url

    def __str__(self):
        return f"{self.website}: {self.original_name}"


class WebsiteMenu(TimeStampedModel):
    """Editable menu with an immutable public item snapshot."""

    class Location(models.TextChoices):
        HEADER = "HEADER", "Cabecera"
        FOOTER = "FOOTER", "Pie de página"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Borrador"
        PUBLISHED = "PUBLISHED", "Publicado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name="menus")
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=20, choices=Location.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    enabled = models.BooleanField(default=True)
    draft_version = models.PositiveIntegerField(default=1)
    published_version = models.PositiveIntegerField(default=0)
    published_items = models.JSONField(default=list, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "website_menus"
        ordering = ("location", "name")
        constraints = [
            models.UniqueConstraint(fields=("website", "location"), name="uniq_menu_location_per_website")
        ]

    def __str__(self):
        return f"{self.website}: {self.name}"


class WebsiteMenuItem(TimeStampedModel):
    class TargetType(models.TextChoices):
        PAGE = "PAGE", "Página"
        URL = "URL", "URL"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    menu = models.ForeignKey(WebsiteMenu, on_delete=models.CASCADE, related_name="items")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="children")
    position = models.PositiveIntegerField()
    label = models.CharField(max_length=80)
    target_type = models.CharField(max_length=20, choices=TargetType.choices)
    page = models.ForeignKey(WebsitePage, on_delete=models.PROTECT, null=True, blank=True, related_name="menu_items")
    url = models.CharField(max_length=1000, blank=True)
    open_in_new_tab = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "website_menu_items"
        ordering = ("position",)
        constraints = [
            models.UniqueConstraint(fields=("menu", "parent", "position"), name="uniq_menu_item_position")
        ]

    def clean(self):
        super().clean()
        if self.target_type == self.TargetType.PAGE:
            if not self.page_id or self.page.website_id != self.menu.website_id:
                raise ValidationError({"page": "Seleccione una página del mismo sitio web."})
            self.url = ""
        elif self.target_type == self.TargetType.URL:
            if not self.url.startswith(("/", "https://")) or self.url.startswith("//"):
                raise ValidationError({"url": "Use una ruta interna o una URL HTTPS."})
            self.page = None
        if self.parent_id:
            if self.parent.menu_id != self.menu_id or self.parent.parent_id:
                raise ValidationError({"parent": "Sólo se permite un nivel de submenú."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.label


class WebsiteCatalogSettings(TimeStampedModel):
    """Public catalog policy without copying ERP pricing or stock."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    website = models.OneToOneField(
        Website, on_delete=models.CASCADE, related_name="catalog_settings"
    )
    default_price_list = models.ForeignKey(
        "inventory.PriceList", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="website_catalog_defaults",
    )
    warehouses = models.ManyToManyField(
        "inventory.Warehouse", blank=True, related_name="website_catalogs"
    )
    show_out_of_stock = models.BooleanField(default=True)
    products_per_page = models.PositiveSmallIntegerField(default=24)

    class Meta:
        db_table = "website_catalog_settings"

    def clean(self):
        super().clean()
        if (
            self.default_price_list_id
            and self.default_price_list.company_id != self.website.company_id
        ):
            raise ValidationError({
                "default_price_list": "La lista de precios debe pertenecer a la empresa del sitio."
            })
        if not 1 <= self.products_per_page <= 60:
            raise ValidationError({"products_per_page": "Use un valor entre 1 y 60."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Catálogo de {self.website}"


class WebsiteProduct(TimeStampedModel):
    """Explicit publication of one ERP product on one website."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    website = models.ForeignKey(
        Website, on_delete=models.CASCADE, related_name="website_products"
    )
    product = models.ForeignKey(
        "inventory.Product", on_delete=models.CASCADE, related_name="website_publications"
    )
    price_list = models.ForeignKey(
        "inventory.PriceList", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="website_product_overrides",
    )
    slug = models.SlugField(max_length=180)
    commercial_title = models.CharField(max_length=180, blank=True)
    commercial_description = models.CharField(max_length=1000, blank=True)
    seo_title = models.CharField(max_length=70, blank=True)
    seo_description = models.CharField(max_length=170, blank=True)
    is_published = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "website_products"
        ordering = ("position", "product__name")
        constraints = [
            models.UniqueConstraint(
                fields=("website", "product"), name="uniq_product_per_website"
            ),
            models.UniqueConstraint(
                fields=("website", "slug"), name="uniq_product_slug_per_website"
            ),
        ]
        indexes = [
            models.Index(
                fields=("website", "is_published", "position"),
                name="idx_web_product_public",
            ),
            models.Index(fields=("website", "slug"), name="idx_web_product_slug"),
        ]

    def clean(self):
        super().clean()
        if self.product_id and self.product.company_id != self.website.company_id:
            raise ValidationError({"product": "El producto debe pertenecer a la empresa del sitio."})
        if self.price_list_id and self.price_list.company_id != self.website.company_id:
            raise ValidationError({
                "price_list": "La lista de precios debe pertenecer a la empresa del sitio."
            })

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(f"{self.product.name}-{self.product.sku}")[:160] or str(self.product_id)
            candidate = base
            suffix = 2
            while type(self).objects.exclude(pk=self.pk).filter(
                website_id=self.website_id, slug=candidate
            ).exists():
                candidate = f"{base[:170 - len(str(suffix))]}-{suffix}"
                suffix += 1
            self.slug = candidate
        else:
            self.slug = slugify(self.slug)
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def public_name(self):
        return self.commercial_title or self.product.name

    @property
    def public_description(self):
        return self.commercial_description or self.product.description

    def __str__(self):
        return f"{self.website}: {self.product}"
