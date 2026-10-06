from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.companies.models import Company, Store, UserCompanyAccess
from apps.inventory.forms import ProductForm
from apps.inventory.models import Product, ProductUnit, Unit
from apps.inventory.product_image_storage import (
    ProductImageUpload,
    build_product_image_key,
    build_product_thumbnail_key,
    build_public_url,
)
from apps.inventory.product_image_storage import upload_product_image
from apps.users.models import User, UserStore


def make_image(name="product.png", content_type="image/png", size=(20, 20), image_format="PNG"):
    output = BytesIO()
    Image.new("RGB", size, "red").save(output, format=image_format)
    return SimpleUploadedFile(name, output.getvalue(), content_type=content_type)


@override_settings(
    R2_PUBLIC_BASE_URL="https://media.apudig.com",
    PRODUCT_IMAGE_MAX_SIZE=5 * 1024 * 1024,
)
class ProductImageTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Images Co", ruc="20123456789")
        self.other_company = Company.objects.create(name="Other Co", ruc="20987654321")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.unit = Unit.objects.create(code="IMG", name="Unidad imagen")
        self.user = User.objects.create_user(email="images@test.com", password="pass")
        UserCompanyAccess.objects.create(
            user=self.user, company=self.company, store=self.store, is_default=True
        )
        UserStore.objects.create(
            user=self.user, store=self.store, role="ADMIN", is_active=True
        )
        self.client.login(username="images@test.com", password="pass")
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()

    def product_data(self, **overrides):
        data = {
            "name": "Producto con imagen",
            "sku": "IMG-01",
            "barcode": "",
            "description": "",
            "model": "",
            "price_purchase": "10.00",
            "price_sale": "15.00",
            "tax_affectation": "10",
            "category": "",
            "brand": "",
            "unit": str(self.unit.pk),
            "active": "on",
            "units-TOTAL_FORMS": "0",
            "units-INITIAL_FORMS": "0",
            "units-MIN_NUM_FORMS": "0",
            "units-MAX_NUM_FORMS": "1000",
        }
        data.update(overrides)
        return data

    def test_public_url_is_built_from_key(self):
        key = "products/company/product/main.webp"
        self.assertEqual(build_public_url(key), f"https://media.apudig.com/{key}")

    def test_product_without_image_has_empty_url(self):
        product = Product(company=self.company, unit=self.unit)
        self.assertEqual(product.image, "")

    def test_product_image_slots_use_distinct_stable_keys(self):
        product = Product(company=self.company, unit=self.unit)
        base = f"products/{self.company.pk}/{product.pk}"
        self.assertEqual(build_product_image_key(product), f"{base}/main.webp")
        self.assertEqual(build_product_image_key(product, "secondary"), f"{base}/secondary.webp")
        self.assertEqual(build_product_image_key(product, "tertiary"), f"{base}/tertiary.webp")
        self.assertEqual(build_product_thumbnail_key(product), f"{base}/main-thumbnail.webp")

    def test_product_thumbnail_falls_back_to_full_image_for_legacy_product(self):
        product = Product(
            company=self.company,
            unit=self.unit,
            image_key="products/legacy/main.webp",
        )

        self.assertEqual(product.image_thumbnail, product.image)

    def test_form_uses_detected_image_type_instead_of_declared_mime(self):
        form = ProductForm(
            data=self.product_data(),
            files={"image_file": make_image(content_type="application/octet-stream")},
            company=self.company,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_rejects_disallowed_format_by_content(self):
        form = ProductForm(
            data=self.product_data(),
            files={
                "image_file": make_image(
                    name="product.jpg",
                    content_type="image/jpeg",
                    image_format="GIF",
                )
            },
            company=self.company,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Formato no permitido", form.errors["image_file"][0])

    def test_form_rejects_corrupt_image(self):
        corrupt = SimpleUploadedFile("broken.jpg", b"not-an-image", content_type="image/jpeg")
        form = ProductForm(
            data=self.product_data(), files={"image_file": corrupt}, company=self.company
        )

        self.assertFalse(form.is_valid())
        self.assertIn("corrupto", form.errors["image_file"][0])

    @override_settings(PRODUCT_IMAGE_MAX_SOURCE_DIMENSION=10)
    def test_form_rejects_excessive_source_dimension(self):
        form = ProductForm(
            data=self.product_data(),
            files={"image_file": make_image(size=(20, 5))},
            company=self.company,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("dimensión máxima", form.errors["image_file"][0])

    @override_settings(PRODUCT_IMAGE_MAX_PIXELS=100)
    def test_form_rejects_excessive_pixel_count(self):
        form = ProductForm(
            data=self.product_data(),
            files={"image_file": make_image(size=(20, 20))},
            company=self.company,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("demasiados píxeles", form.errors["image_file"][0])

    @override_settings(PRODUCT_IMAGE_MAX_SIZE=10)
    def test_form_rejects_oversized_image(self):
        form = ProductForm(
            data=self.product_data(),
            files={"image_file": make_image()},
            company=self.company,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("no debe superar", form.errors["image_file"][0])

    def test_form_accepts_valid_image(self):
        form = ProductForm(
            data=self.product_data(),
            files={"image_file": make_image()},
            company=self.company,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_product_form_has_mobile_image_actions_and_processing_status(self):
        product = Product.objects.create(
            company=self.company,
            unit=self.unit,
            name="Producto editable",
            sku="IMG-EDIT",
        )

        for url in (
            reverse("inventory:product_create"),
            reverse("inventory:product_update", args=[product.pk]),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'capture="environment"', count=3)
                self.assertContains(response, 'class="visually-hidden product-camera-input"', count=3)
                self.assertContains(response, "Tomar foto", count=3)
                self.assertContains(response, "Elegir de galería", count=3)
                self.assertContains(response, 'class="visually-hidden product-image-input"', count=3)
                self.assertContains(response, 'class="image-processing-status small mt-1"', count=3)

    @override_settings(
        R2_ACCOUNT_ID="account",
        R2_ACCESS_KEY_ID="access",
        R2_SECRET_ACCESS_KEY="secret",
        R2_BUCKET_NAME="products-bucket",
        PRODUCT_IMAGE_MAX_DIMENSION=1200,
        PRODUCT_IMAGE_WEBP_QUALITY=82,
        PRODUCT_IMAGE_THUMBNAIL_DIMENSION=480,
        PRODUCT_IMAGE_THUMBNAIL_QUALITY=78,
    )
    @patch("apps.inventory.product_image_storage._get_r2_client")
    def test_upload_uses_mocked_r2_and_webp_payload(self, client_factory):
        product = Product(
            company=self.company,
            unit=self.unit,
            name="Optimizado",
            sku="OPT-01",
        )
        uploaded = upload_product_image(product, make_image(size=(1400, 700)))

        self.assertEqual(
            uploaded.image_key, f"products/{self.company.pk}/{product.pk}/main.webp"
        )
        self.assertEqual(
            uploaded.thumbnail_key,
            f"products/{self.company.pk}/{product.pk}/main-thumbnail.webp",
        )
        calls = client_factory.return_value.put_object.call_args_list
        self.assertEqual(len(calls), 2)
        image_kwargs = calls[0].kwargs
        thumbnail_kwargs = calls[1].kwargs
        self.assertEqual(image_kwargs["Bucket"], "products-bucket")
        self.assertEqual(image_kwargs["Key"], uploaded.image_key)
        self.assertEqual(thumbnail_kwargs["Key"], uploaded.thumbnail_key)
        self.assertEqual(image_kwargs["ContentType"], "image/webp")
        with Image.open(BytesIO(image_kwargs["Body"])) as optimized:
            self.assertEqual(optimized.format, "WEBP")
            self.assertEqual(optimized.size, (1200, 600))
        with Image.open(BytesIO(thumbnail_kwargs["Body"])) as thumbnail:
            self.assertEqual(thumbnail.format, "WEBP")
            self.assertEqual(thumbnail.size, (480, 240))

    @patch("apps.inventory.views.masters.upload_product_image")
    def test_create_uploads_image_and_saves_only_key(self, upload_mock):
        expected_key = "products/company/product/main.webp"
        expected_thumbnail_key = "products/company/product/main-thumbnail.webp"
        upload_mock.return_value = ProductImageUpload(expected_key, expected_thumbnail_key)
        response = self.client.post(
            reverse("inventory:product_create"),
            data={**self.product_data(), "image_file": make_image()},
        )
        self.assertRedirects(response, reverse("inventory:product_list"))
        product = Product.objects.get(sku="IMG-01")
        self.assertEqual(product.image_key, expected_key)
        self.assertEqual(product.image_thumbnail_key, expected_thumbnail_key)
        conversion = ProductUnit.objects.get(product=product, unit=self.unit)
        self.assertTrue(conversion.is_default_sale)
        self.assertTrue(conversion.is_default_purchase)
        upload_mock.assert_called_once()
        self.assertEqual(upload_mock.call_args.args[0].company_id, self.company.pk)

    @patch("apps.inventory.views.masters.upload_product_image")
    def test_create_accepts_three_product_images(self, upload_mock):
        def uploaded_key(product, uploaded_file, slot="main"):
            filename = {"main": "main.webp", "secondary": "secondary.webp", "tertiary": "tertiary.webp"}[slot]
            thumbnail = {
                "main": "main-thumbnail.webp",
                "secondary": "secondary-thumbnail.webp",
                "tertiary": "tertiary-thumbnail.webp",
            }[slot]
            base = f"products/{product.company_id}/{product.pk}"
            return ProductImageUpload(f"{base}/{filename}", f"{base}/{thumbnail}")

        upload_mock.side_effect = uploaded_key
        response = self.client.post(
            reverse("inventory:product_create"),
            data={
                **self.product_data(sku="IMG-03"),
                "image_file": make_image("main.png"),
                "secondary_image_file": make_image("secondary.png"),
                "tertiary_image_file": make_image("tertiary.png"),
            },
        )
        self.assertRedirects(response, reverse("inventory:product_list"))
        product = Product.objects.get(sku="IMG-03")
        self.assertTrue(product.image_key.endswith("/main.webp"))
        self.assertTrue(product.secondary_image_key.endswith("/secondary.webp"))
        self.assertTrue(product.tertiary_image_key.endswith("/tertiary.webp"))
        self.assertTrue(product.image_thumbnail_key.endswith("/main-thumbnail.webp"))
        self.assertTrue(product.secondary_image_thumbnail_key.endswith("/secondary-thumbnail.webp"))
        self.assertTrue(product.tertiary_image_thumbnail_key.endswith("/tertiary-thumbnail.webp"))
        self.assertEqual(upload_mock.call_count, 3)

    @patch("apps.inventory.views.masters.upload_product_image")
    def test_cannot_update_product_image_from_another_company(self, upload_mock):
        product = Product.objects.create(
            company=self.other_company,
            unit=self.unit,
            name="Ajeno",
            sku="OTHER-01",
        )
        response = self.client.post(
            reverse("inventory:product_update", args=[product.pk]),
            data={**self.product_data(), "image_file": make_image()},
        )
        self.assertEqual(response.status_code, 404)
        upload_mock.assert_not_called()
