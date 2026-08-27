from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.companies.models import Company, Store, UserCompanyAccess
from apps.inventory.forms import ProductForm
from apps.inventory.models import Product, ProductUnit, Unit
from apps.inventory.product_image_storage import build_product_image_key, build_public_url
from apps.inventory.product_image_storage import upload_product_image
from apps.users.models import User


def make_image(name="product.png", content_type="image/png", size=(20, 20)):
    output = BytesIO()
    Image.new("RGB", size, "red").save(output, format="PNG")
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
            "category": "",
            "brand": "",
            "unit": str(self.unit.pk),
            "active": "on",
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

    def test_form_rejects_invalid_mime_type(self):
        form = ProductForm(
            data=self.product_data(),
            files={"image_file": make_image(content_type="application/octet-stream")},
            company=self.company,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Formato no permitido", form.errors["image_file"][0])

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

    @override_settings(
        R2_ACCOUNT_ID="account",
        R2_ACCESS_KEY_ID="access",
        R2_SECRET_ACCESS_KEY="secret",
        R2_BUCKET_NAME="products-bucket",
        PRODUCT_IMAGE_MAX_DIMENSION=1200,
        PRODUCT_IMAGE_WEBP_QUALITY=82,
    )
    @patch("apps.inventory.product_image_storage._get_r2_client")
    def test_upload_uses_mocked_r2_and_webp_payload(self, client_factory):
        product = Product(
            company=self.company,
            unit=self.unit,
            name="Optimizado",
            sku="OPT-01",
        )
        key = upload_product_image(product, make_image(size=(1400, 700)))

        self.assertEqual(
            key, f"products/{self.company.pk}/{product.pk}/main.webp"
        )
        put_kwargs = client_factory.return_value.put_object.call_args.kwargs
        self.assertEqual(put_kwargs["Bucket"], "products-bucket")
        self.assertEqual(put_kwargs["Key"], key)
        self.assertEqual(put_kwargs["ContentType"], "image/webp")
        with Image.open(BytesIO(put_kwargs["Body"])) as optimized:
            self.assertEqual(optimized.format, "WEBP")
            self.assertEqual(optimized.size, (1200, 600))

    @patch("apps.inventory.views.masters.upload_product_image")
    def test_create_uploads_image_and_saves_only_key(self, upload_mock):
        expected_key = "products/company/product/main.webp"
        upload_mock.return_value = expected_key
        response = self.client.post(
            reverse("inventory:product_create"),
            data={**self.product_data(), "image_file": make_image()},
        )
        self.assertRedirects(response, reverse("inventory:product_list"))
        product = Product.objects.get(sku="IMG-01")
        self.assertEqual(product.image_key, expected_key)
        conversion = ProductUnit.objects.get(product=product, unit=self.unit)
        self.assertTrue(conversion.is_default_sale)
        self.assertTrue(conversion.is_default_purchase)
        upload_mock.assert_called_once()
        self.assertEqual(upload_mock.call_args.args[0].company_id, self.company.pk)

    @patch("apps.inventory.views.masters.upload_product_image")
    def test_create_accepts_three_product_images(self, upload_mock):
        def uploaded_key(product, uploaded_file, slot="main"):
            filename = {"main": "main.webp", "secondary": "secondary.webp", "tertiary": "tertiary.webp"}[slot]
            return f"products/{product.company_id}/{product.pk}/{filename}"

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
