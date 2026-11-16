import django.core.validators
import django.db.models.deletion
import uuid

from django.conf import settings
from django.db import migrations, models
from django.utils.text import slugify


PERMISSIONS = (
    ("read.website", "read", "website", "Consultar la configuraciÃ³n del sitio web"),
    ("manage.website", "manage", "website", "Gestionar la configuraciÃ³n del sitio web"),
    (
        "manage.website.domains",
        "manage",
        "website.domains",
        "Gestionar dominios del sitio web",
    ),
)


def seed_website_foundations(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Role = apps.get_model("users", "Role")
    RolePermission = apps.get_model("users", "RolePermission")
    Website = apps.get_model("websites", "Website")
    WebsiteSettings = apps.get_model("websites", "WebsiteSettings")

    permissions = []
    for code, action, module, description in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "action_name": action,
                "module": module,
                "description": description,
            },
        )
        permissions.append(permission)

    admin_roles = Role.objects.filter(
        models.Q(name__iexact="ADMIN") | models.Q(name__iexact="SUPERUSER")
    )
    for role in admin_roles:
        for permission in permissions:
            RolePermission.objects.get_or_create(role=role, permission=permission)

    for website in Website.objects.all().iterator():
        if not website.slug:
            base = slugify(website.name)[:100] or "website"
            website.slug = f"{base}-{str(website.company_id)[:8]}"
            website.save(update_fields=("slug",))
        WebsiteSettings.objects.get_or_create(
            website=website,
            defaults={"business_name": website.name},
        )


def remove_website_permissions(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Permission.objects.filter(code__in=[item[0] for item in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("users", "0005_useroperationalflags_can_correct_pos_payment"),
        ("websites", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="website",
            name="slug",
            field=models.SlugField(blank=True, max_length=140),
        ),
        migrations.AddField(
            model_name="website",
            name="default_locale",
            field=models.CharField(default="es-PE", max_length=15),
        ),
        migrations.AddField(
            model_name="website",
            name="timezone",
            field=models.CharField(default="America/Lima", max_length=64),
        ),
        migrations.AddField(
            model_name="website",
            name="currency",
            field=models.CharField(default="PEN", max_length=3),
        ),
        migrations.AddField(
            model_name="website",
            name="published_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="website",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="websites_created",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="website",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="websites_updated",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="website",
            constraint=models.UniqueConstraint(
                condition=~models.Q(slug=""),
                fields=("slug",),
                name="uniq_nonempty_website_slug",
            ),
        ),
        migrations.AddField(
            model_name="websitedomain",
            name="kind",
            field=models.CharField(
                choices=[
                    ("SUBDOMAIN", "Subdominio APUDIG"),
                    ("CUSTOM", "Dominio personalizado"),
                    ("ALIAS", "Alias"),
                ],
                default="SUBDOMAIN",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="websitedomain",
            name="verification_method",
            field=models.CharField(
                choices=[("DNS_TXT", "Registro DNS TXT")],
                default="DNS_TXT",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="websitedomain",
            name="verification_token_hash",
            field=models.CharField(blank=True, editable=False, max_length=128),
        ),
        migrations.AddField(
            model_name="websitedomain",
            name="last_verification_error",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AlterField(
            model_name="websitedomain",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pendiente"),
                    ("VERIFYING", "Verificando"),
                    ("VERIFIED", "Verificado"),
                    ("ACTIVE", "Activo"),
                    ("FAILED", "Fallido"),
                    ("DISABLED", "Deshabilitado"),
                ],
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="WebsiteSettings",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("business_name", models.CharField(blank=True, max_length=255)),
                ("logo_url", models.URLField(blank=True, max_length=1000)),
                ("favicon_url", models.URLField(blank=True, max_length=1000)),
                ("primary_color", models.CharField(default="#0B1F3A", max_length=7, validators=[django.core.validators.RegexValidator(message="Use un color hexadecimal de seis dÃ­gitos, por ejemplo #0B1F3A.", regex="^#[0-9A-Fa-f]{6}$")])),
                ("accent_color", models.CharField(default="#F97316", max_length=7, validators=[django.core.validators.RegexValidator(message="Use un color hexadecimal de seis dÃ­gitos, por ejemplo #0B1F3A.", regex="^#[0-9A-Fa-f]{6}$")])),
                ("background_color", models.CharField(default="#FFFFFF", max_length=7, validators=[django.core.validators.RegexValidator(message="Use un color hexadecimal de seis dÃ­gitos, por ejemplo #0B1F3A.", regex="^#[0-9A-Fa-f]{6}$")])),
                ("text_color", models.CharField(default="#111827", max_length=7, validators=[django.core.validators.RegexValidator(message="Use un color hexadecimal de seis dÃ­gitos, por ejemplo #0B1F3A.", regex="^#[0-9A-Fa-f]{6}$")])),
                ("whatsapp", models.CharField(blank=True, max_length=30)),
                ("phone", models.CharField(blank=True, max_length=30)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("address", models.CharField(blank=True, max_length=500)),
                ("business_hours", models.JSONField(blank=True, default=dict)),
                ("social_links", models.JSONField(blank=True, default=dict)),
                ("default_seo_title", models.CharField(blank=True, max_length=70)),
                ("default_seo_description", models.CharField(blank=True, max_length=170)),
                ("website", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="settings", to="websites.website")),
            ],
            options={"db_table": "website_settings"},
        ),
        migrations.RunPython(seed_website_foundations, remove_website_permissions),
    ]
