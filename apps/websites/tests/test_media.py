from io import BytesIO
from unittest.mock import Mock, patch

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import override_settings

from apps.core.models import AuditLog
from apps.users.models import RolePermission
from apps.websites import media_storage
from apps.websites.models import WebsiteMedia
from .test_editorial import EditorialTestCase


def image_file(color="red", size=(24, 24)):
    stream = BytesIO()
    Image.new("RGB", size, color).save(stream, format="PNG")
    return SimpleUploadedFile("banner.png", stream.getvalue(), content_type="image/png")


@override_settings(R2_PUBLIC_BASE_URL="https://media.example.com")
class WebsiteMediaTest(EditorialTestCase):
    def setUp(self):
        super().setUp()
        self.storage = Mock()
        self.mock = patch("apps.websites.media_storage.create_r2_client", return_value=self.storage)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def upload(self, file=None):
        return self.client.post(self.url("media"), {"file": file or image_file(), "kind": "IMAGE", "altText": "Banner autorizado"})

    def test_upload_uses_persistent_company_prefix_and_preserves_old_media_keys(self):
        self.website.storage_prefix = "ft_soledad"
        self.website.save()
        response = self.client.post(self.url("media"), {"file": image_file(), "kind": "BANNER", "altText": "Banner"})
        self.assertEqual(response.status_code, 201, response.content)
        media = WebsiteMedia.objects.get(pk=response.json()["id"])
        self.assertTrue(media.storage_key.startswith("ft_soledad/website/banners/"))
        self.assertTrue(media.thumbnail_key.endswith("-thumbnail.webp"))
        self.assertEqual(response.json()["url"], f"https://media.example.com/{media.storage_key}")
        self.document["banners"][0].update(imageUrl=media.url, imageAlt="Banner")
        self.assertEqual(self.save_document().status_code, 200)
        self.assertEqual(self.client.delete(self.url("media") + str(media.pk) + "/").status_code, 409)

    def test_upload_optimizes_and_returns_only_managed_metadata(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.storage.put_object.call_count, 2)
        result = response.json()
        self.assertEqual(result["mimeType"], "image/webp")
        self.assertEqual(result["websiteId"], str(self.website.pk))
        self.assertNotIn("storage_key", result)
        body = self.storage.put_object.call_args_list[0].kwargs["Body"]
        with Image.open(BytesIO(body)) as image:
            self.assertEqual(image.format, "WEBP")
        self.assertEqual(self.client.get(self.url("media")).json()["count"], 1)
        self.assertEqual(AuditLog.objects.filter(action="WEBSITE_MEDIA_UPLOAD").count(), 1)

    def test_identical_upload_deduplicates_without_new_objects(self):
        first = self.upload()
        second = self.upload()
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(self.storage.put_object.call_count, 2)
        self.assertEqual(WebsiteMedia.objects.count(), 1)

    def test_owner_reference_roundtrip_and_retention_after_draft_changes(self):
        asset = self.upload().json()
        self.document["banners"][0].update(imageUrl=asset["url"], imageAlt="Banner de la empresa")
        saved = self.save_document()
        self.assertEqual(saved.status_code, 200, saved.content)
        media = WebsiteMedia.objects.get(pk=asset["id"])
        self.assertTrue(media.draft_references.exists())
        self.assertTrue(media.revision_references.exists())
        self.assertEqual(self.client.delete(self.url("media") + asset["id"] + "/").status_code, 409)
        self.document["banners"][0]["imageUrl"] = ""
        self.save_document(revision=1)
        self.assertFalse(media.draft_references.exists())
        self.assertEqual(self.client.delete(self.url("media") + asset["id"] + "/").status_code, 409)

    def test_media_reference_id_cannot_use_foreign_asset_or_arbitrary_url(self):
        foreign = WebsiteMedia.objects.create(website=self.other, storage_key="foreign.webp", thumbnail_key="foreign-thumb.webp", original_name="foreign.png", checksum="foreign")
        self.document["banners"][0].update(imageUrl=foreign.url, imageAlt="No autorizado")
        response = self.save_document()
        self.assertEqual(response.status_code, 400)
        response = self.save_document(mediaReferences={"banners.banner-principal.imageUrl": str(foreign.pk)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.delete(self.url("media") + str(foreign.pk) + "/").status_code, 404)
        self.document["banners"][0]["imageUrl"] = "https://external.example.com/file.png"
        self.assertEqual(self.save_document().status_code, 400)

    def test_explicit_owned_media_id_derives_url_and_restores(self):
        asset = self.upload().json()
        self.document["banners"][0]["imageAlt"] = "Descripción"
        response = self.save_document(mediaReferences={"banners.banner-principal.imageUrl": asset["id"]})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["draft"]["banners"][0]["imageUrl"], asset["url"])

    def test_unreferenced_media_is_soft_deleted_without_physical_removal(self):
        asset = self.upload().json()
        response = self.client.delete(self.url("media") + asset["id"] + "/")
        self.assertEqual(response.status_code, 204)
        self.assertTrue(WebsiteMedia.objects.get(pk=asset["id"]).is_deleted)
        self.assertEqual(self.client.get(self.url("media")).json()["count"], 0)
        self.storage.delete_object.assert_not_called()

    def test_invalid_files_and_inline_json_rejected(self):
        for filename, body in (("file.svg", b"<svg/>"), ("file.html", b"<script/>"), ("file.png", b"not a png")):
            response = self.upload(SimpleUploadedFile(filename, body, content_type="image/png"))
            self.assertIn(response.status_code, (400, 415))
        response = self.client.post(self.url("media"), {"file": "data:image/png;base64,AAAA"}, content_type="application/json")
        self.assertEqual(response.status_code, 415)
        self.storage.put_object.assert_not_called()

    def test_limits_use_actual_size_and_decoded_dimensions(self):
        with override_settings(PRODUCT_IMAGE_MAX_SIZE=100):
            response = self.upload(SimpleUploadedFile("large.png", b"x" * 101, content_type="image/png"))
            self.assertEqual(response.status_code, 413)
        with override_settings(PRODUCT_IMAGE_MAX_SOURCE_DIMENSION=16):
            self.assertEqual(self.upload(image_file(size=(32, 32))).status_code, 400)
        self.storage.put_object.assert_not_called()

    def test_storage_failure_rolls_back_metadata_and_cleans_attempted_keys(self):
        self.storage.put_object.side_effect = [None, RuntimeError("private storage failure sentinel")]
        response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("sentinel", response.content.decode())
        self.assertEqual(self.storage.delete_object.call_count, 2)
        self.assertFalse(WebsiteMedia.objects.exists())
        self.assertFalse(AuditLog.objects.filter(action="WEBSITE_MEDIA_UPLOAD").exists())

    def test_database_failure_after_upload_cleans_new_objects(self):
        with patch.object(WebsiteMedia.objects, "create", side_effect=IntegrityError("simulated database failure")), self.assertRaises(IntegrityError):
            media_storage.upload_media(**self.service_args(), uploaded_file=image_file())
        self.assertEqual(self.storage.delete_object.call_count, 2)
        self.assertFalse(WebsiteMedia.objects.exists())

    def test_read_permission_cannot_upload_or_delete_media(self):
        RolePermission.objects.filter(role=self.role, permission__code="manage.website.media").delete()
        self.assertEqual(self.upload().status_code, 403)
        self.assertEqual(self.client.get(self.url("media")).status_code, 200)

    @override_settings(R2_PUBLIC_BASE_URL="")
    def test_missing_public_media_url_does_not_upload_unusable_file(self):
        self.assertEqual(self.upload().status_code, 503)
        self.storage.put_object.assert_not_called()
