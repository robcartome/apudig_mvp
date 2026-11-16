from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import connection, close_old_connections
from django.test import TransactionTestCase
from unittest import skipUnless
from unittest.mock import Mock, patch

from apps.companies.models import Company, UserCompanyAccess
from apps.users.models import User, Role, UserRole, RolePermission, Permission
from apps.websites import services, media_storage
from apps.websites.errors import WebsiteError
from apps.websites.models import Website, WebsitePageRevision, WebsiteMedia
from .test_editorial import editorial_fixture
from .test_media import image_file


@skipUnless(connection.vendor == "postgresql", "Requires real PostgreSQL row locking")
class EditorialConcurrencyTest(TransactionTestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Concurrent A", ruc="20999999401")
        self.website = Website.objects.create(company=self.company, name="Concurrent web")
        self.user = User.objects.create_user(email="concurrent@example.com")
        UserCompanyAccess.objects.create(user=self.user, company=self.company)
        role = Role.objects.create(name="Concurrent editorial")
        UserRole.objects.create(user=self.user, role=role, company=self.company)
        for code in ("read.website", "manage.website", "publish.website", "manage.website.media"):
            action, module = code.split(".", 1)
            permission, _ = Permission.objects.get_or_create(code=code, defaults={"action_name": action, "module": module})
            RolePermission.objects.create(role=role, permission=permission)

    def args(self):
        return {"user": self.user, "company_id": self.company.pk, "website_id": self.website.pk}

    def race(self, operations):
        barrier = Barrier(2)

        def worker(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return ("ok", operation())
            except WebsiteError as exc:
                return ("error", exc.status)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, operation) for operation in operations]
            return [future.result(timeout=25) for future in futures]

    def test_two_editors_only_one_can_save_same_revision(self):
        left, right = editorial_fixture(), editorial_fixture()
        left["banners"][0]["title"] = "Editor A"
        right["banners"][0]["title"] = "Editor B"
        results = self.race([
            lambda: services.save_draft(**self.args(), document=left, expected_revision=0),
            lambda: services.save_draft(**self.args(), document=right, expected_revision=0),
        ])
        self.assertEqual(sorted(item[0] for item in results), ["error", "ok"])
        self.assertIn(("error", 412), results)
        self.website.refresh_from_db()
        self.assertEqual(self.website.editorial_revision, 1)
        self.assertEqual(WebsitePageRevision.objects.count(), 1)
        self.assertIn(services.load_editor(**self.args())["draft"]["banners"][0]["title"], ("Editor A", "Editor B"))

    def test_save_competing_with_publish_cannot_mix_snapshots(self):
        document = editorial_fixture()
        services.save_draft(**self.args(), document=document, expected_revision=0)
        changed = editorial_fixture()
        changed["identity"]["name"] = "New identity"
        changed["contact"]["phone"] = "999999999"
        results = self.race([
            lambda: services.save_draft(**self.args(), document=changed, expected_revision=1),
            lambda: services.publish_website(**self.args(), expected_revision=1),
        ])
        self.assertIn(("error", 412), results)
        self.website.refresh_from_db()
        self.assertEqual(self.website.editorial_revision, 2)
        if self.website.published_revision_id:
            self.assertEqual(self.website.published_revision.snapshot["document"], document)
        else:
            self.assertEqual(services.load_editor(**self.args())["draft"], changed)

    def test_concurrent_identical_uploads_create_one_managed_asset(self):
        storage = Mock()
        with patch("apps.websites.media_storage.create_r2_client", return_value=storage):
            results = self.race([
                lambda: media_storage.upload_media(**self.args(), uploaded_file=image_file()),
                lambda: media_storage.upload_media(**self.args(), uploaded_file=image_file()),
            ])
        self.assertTrue(all(status == "ok" for status, _ in results))
        self.assertEqual(sorted(value[1] for _, value in results), [False, True])
        self.assertEqual(WebsiteMedia.objects.count(), 1)
        self.assertEqual(storage.put_object.call_count, 2)
