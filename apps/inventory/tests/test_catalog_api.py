from decimal import Decimal
import datetime

import jwt
from django.conf import settings
from django.test import TestCase

from apps.companies.models import Company, Store, UserCompanyAccess
from apps.inventory.models import (
    Brand,
    Category,
    PriceList,
    Product,
    ProductPrice,
    StockByWarehouse,
    Unit,
    Warehouse,
)
from apps.users.models import User


def _make_employee_token(company_id):
    """Issue a valid employee JWT for tests."""
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": "00000000-0000-0000-0000-000000000001",
        "email": "emp@test.com",
        "company_id": str(company_id),
        "store_id": None,
        "type": "access",
        "iat": now,
        "exp": now + datetime.timedelta(hours=1),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


class CatalogApiTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Catalog Co", ruc="20111111111")
        self.store = Store.objects.create(company=self.company, name="Tienda Central")
        self.unit = Unit.objects.create(code="NIU", name="Unidad")
        self.category = Category.objects.create(company=self.company, code="CAT01", name="Ferreteria")
        self.brand = Brand.objects.create(company=self.company, name="Marca A")
        self.product = Product.objects.create(
            company=self.company,
            name="Taladro",
            sku="TAL-01",
            unit=self.unit,
            category=self.category,
            brand=self.brand,
            price_purchase=Decimal("120.00"),
            price_sale=Decimal("160.00"),
            active=True,
        )
        self.warehouse = Warehouse.objects.create(store=self.store, name="Almacen Principal")
        StockByWarehouse.objects.create(product=self.product, warehouse=self.warehouse, quantity=Decimal("8.500"))

        self.price_list = PriceList.objects.create(company=self.company, name="Mayorista", active=True)
        ProductPrice.objects.create(
            product=self.product,
            price_list=self.price_list,
            amount=Decimal("150.00"),
            currency="PEN",
            active=True,
        )

        # Employee user linked to company
        self.user = User.objects.create_user(email="emp@test.com", password="pass")
        UserCompanyAccess.objects.create(user=self.user, company=self.company, store=self.store, is_default=True)
        self.employee_token = _make_employee_token(self.company.pk)

    def test_catalog_products_returns_paginated_payload(self):
        # ── Public access: price_purchase NOT returned ─────────────────────
        resp = self.client.get("/catalog/products", {"search": "tala", "limit": 10, "offset": 0})

        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["total"], 1)
        self.assertEqual(data["limit"], 10)
        self.assertEqual(data["offset"], 0)
        self.assertEqual(len(data["results"]), 1)

        item = data["results"][0]
        self.assertEqual(item["id"], str(self.product.pk))
        self.assertEqual(item["name"], "Taladro")
        self.assertEqual(item["sku"], "TAL-01")
        self.assertEqual(item["unit"], "NIU")
        self.assertEqual(item["brand"], "Marca A")
        self.assertEqual(item["category"], "Ferreteria")
        self.assertEqual(item["price_sale"], "160.00")
        self.assertEqual(item["stock"], 8.5)
        self.assertNotIn("price_purchase", item)  # hidden for public

    def test_catalog_products_employee_sees_price_purchase(self):
        # ── Employee access: price_purchase IS returned ───────────────────
        resp = self.client.get(
            "/catalog/products",
            {"search": "tala", "limit": 10, "offset": 0},
            HTTP_AUTHORIZATION=f"Bearer {self.employee_token}",
        )

        self.assertEqual(resp.status_code, 200)
        item = resp.json()["results"][0]
        self.assertEqual(item["price_purchase"], "120.00")
        self.assertEqual(item["price_sale"], "160.00")

    def test_catalog_product_detail_returns_expected_shape(self):
        # ── Public: price_purchase absent ────────────────────────────────
        resp = self.client.get(f"/catalog/products/{self.product.pk}/detail")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["id"], str(self.product.pk))
        self.assertEqual(data["name"], "Taladro")
        self.assertEqual(data["unit"], "NIU")
        self.assertEqual(data["brand"], "Marca A")
        self.assertEqual(data["category"], "Ferreteria")
        self.assertEqual(data["price_sale"], "160.00")
        self.assertNotIn("price_purchase", data)  # hidden for public
        self.assertEqual(data["stock_total"], 8.5)
        self.assertEqual(len(data["price_list"]), 1)
        self.assertEqual(data["price_list"][0]["price_list_name"], "Mayorista")
        self.assertEqual(data["price_list"][0]["amount"], "150.00")
        self.assertEqual(data["price_list"][0]["currency"], "PEN")
        self.assertEqual(len(data["stock_by_warehouse"]), 1)
        self.assertEqual(data["stock_by_warehouse"][0]["warehouse_name"], "Almacen Principal")
        self.assertEqual(data["stock_by_warehouse"][0]["quantity"], 8.5)

    def test_catalog_product_detail_employee_sees_price_purchase(self):
        # ── Employee: price_purchase present ─────────────────────────────
        resp = self.client.get(
            f"/catalog/products/{self.product.pk}/detail",
            HTTP_AUTHORIZATION=f"Bearer {self.employee_token}",
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["price_purchase"], "120.00")

    def test_catalog_product_detail_not_found(self):
        resp = self.client.get("/catalog/products/11111111-1111-1111-1111-111111111111/detail")
        self.assertEqual(resp.status_code, 404)