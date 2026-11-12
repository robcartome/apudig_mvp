import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_pages_permission_and_home(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Role = apps.get_model("users", "Role")
    RolePermission = apps.get_model("users", "RolePermission")
    Website = apps.get_model("websites", "Website")
    WebsitePage = apps.get_model("websites", "WebsitePage")

    permission, _ = Permission.objects.update_or_create(
        code="publish.website",
        defaults={"action_name": "publish", "module": "website", "description": "Publicar páginas del sitio web"},
    )
    for role in Role.objects.filter(models.Q(name__iexact="ADMIN") | models.Q(name__iexact="SUPERUSER")):
        RolePermission.objects.get_or_create(role=role, permission=permission)
    for website in Website.objects.all().iterator():
        WebsitePage.objects.get_or_create(
            website=website, page_type="HOME",
            defaults={"slug": "home", "title": "Inicio"},
        )


def remove_publish_permission(apps, schema_editor):
    apps.get_model("users", "Permission").objects.filter(code="publish.website").delete()


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("users", "0005_useroperationalflags_can_correct_pos_payment"),
        ("websites", "0002_website_foundations"),
    ]

    operations = [
        migrations.CreateModel(
            name="WebsitePage",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("slug", models.SlugField(max_length=140)),
                ("title", models.CharField(max_length=160)),
                ("page_type", models.CharField(choices=[("HOME", "Inicio"), ("STANDARD", "Estándar"), ("CONTACT", "Contacto")], default="STANDARD", max_length=20)),
                ("status", models.CharField(choices=[("DRAFT", "Borrador"), ("PUBLISHED", "Publicado"), ("ARCHIVED", "Archivado")], default="DRAFT", max_length=20)),
                ("seo_title", models.CharField(blank=True, max_length=70)),
                ("seo_description", models.CharField(blank=True, max_length=170)),
                ("og_image_url", models.URLField(blank=True, max_length=1000)),
                ("noindex", models.BooleanField(default=False)),
                ("draft_version", models.PositiveIntegerField(default=1)),
                ("published_version", models.PositiveIntegerField(default=0)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="website_pages_created", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="website_pages_updated", to=settings.AUTH_USER_MODEL)),
                ("website", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pages", to="websites.website")),
            ],
            options={"db_table": "website_pages", "ordering": ("page_type", "title")},
        ),
        migrations.CreateModel(
            name="WebsiteSection",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("section_type", models.CharField(max_length=60)),
                ("schema_version", models.PositiveSmallIntegerField(default=1)),
                ("position", models.PositiveIntegerField()),
                ("enabled", models.BooleanField(default=True)),
                ("config", models.JSONField(default=dict)),
                ("page", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sections", to="websites.websitepage")),
            ],
            options={"db_table": "website_sections", "ordering": ("position",)},
        ),
        migrations.CreateModel(
            name="WebsitePageRevision",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("version", models.PositiveIntegerField()),
                ("snapshot", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="website_page_revisions_created", to=settings.AUTH_USER_MODEL)),
                ("page", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="revisions", to="websites.websitepage")),
            ],
            options={"db_table": "website_page_revisions", "ordering": ("-version",)},
        ),
        migrations.AddConstraint(model_name="websitepage", constraint=models.UniqueConstraint(fields=("website", "slug"), name="uniq_page_slug_per_website")),
        migrations.AddConstraint(model_name="websitepage", constraint=models.UniqueConstraint(condition=models.Q(("page_type", "HOME")), fields=("website",), name="uniq_home_page_per_website")),
        migrations.AddConstraint(model_name="websitesection", constraint=models.UniqueConstraint(fields=("page", "position"), name="uniq_section_position_per_page")),
        migrations.AddConstraint(model_name="websitepagerevision", constraint=models.UniqueConstraint(fields=("page", "version"), name="uniq_revision_version_per_page")),
        migrations.RunPython(seed_pages_permission_and_home, remove_publish_permission),
    ]
