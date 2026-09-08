"""
inventory/tests/test_operations.py — Tests de movimientos y stock.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Store, UserCompanyAccess
from apps.inventory.models import Movement, Product, StockByWarehouse, Unit, Warehouse
from apps.users.models import User


class MovementViewsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="ops@demo.com", password="testpass")
        self.company = Company.objects.create(name="Demo Ops", ruc="20999999903")
        self.store = Store.objects.create(company=self.company, name="Principal")
        UserCompanyAccess.objects.create(
            user=self.user, company=self.company, store=self.store, is_default=True
        )
        self.unit = Unit.objects.create(code="UND", name="Unidad")
        self.warehouse = Warehouse.objects.create(store=self.store, name="Almacén A")
        self.product = Product.objects.create(
            company=self.company,
            name="Producto Test", sku="TEST-01", unit=self.unit,
            price_purchase=Decimal("10"), price_sale=Decimal("15"),
        )

        self.client.login(username="ops@demo.com", password="testpass")
        session = self.client.session
        session["active_company_id"] = str(self.company.id)
        session["active_store_id"] = str(self.store.id)
        session.save()

    def _post_movement(self, url, extra_data=None):
        now = timezone.now().strftime("%Y-%m-%dT%H:%M")
        data = {
            "date": now,
            "warehouse": str(self.warehouse.pk),
            "reason": "Test",
            "reference_doc": "",
            "supplier": "",
            "customer": "",
            "carrier": "",
            "document_type": "",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.pk),
            "lines-0-quantity": "5",
            "lines-0-unit_price": "10",
        }
        if extra_data:
            data.update(extra_data)
        return self.client.post(url, data)

    # ── Movement list ─────────────────────────────────────────────────────────

    def test_movement_list_ok(self):
        resp = self.client.get(reverse("inventory:movement_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Fecha de creación")
        self.assertContains(resp, "Fecha de movimiento")
        self.assertContains(resp, 'name="show_all_dates"', html=False)

    def test_movement_list_can_show_records_outside_current_month(self):
        self._post_movement(
            reverse("inventory:entry_create"),
            {"date": "2020-01-15T10:00"},
        )

        default_response = self.client.get(reverse("inventory:movement_list"))
        all_dates_response = self.client.get(
            reverse("inventory:movement_list"), {"show_all_dates": "1"}
        )

        self.assertEqual(default_response.context["page_obj"].paginator.count, 0)
        self.assertEqual(all_dates_response.context["page_obj"].paginator.count, 1)
        self.assertEqual(all_dates_response.context["list_filters"]["date_from"], "")
        self.assertEqual(all_dates_response.context["list_filters"]["date_to"], "")

    def test_stock_by_warehouse_api_includes_all_company_warehouses(self):
        other_store = Store.objects.create(company=self.company, name="Secundaria")
        other_warehouse = Warehouse.objects.create(store=other_store, name="Almacén B")
        StockByWarehouse.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=Decimal("12.500")
        )

        response = self.client.get(
            reverse("inventory:api_product_stock_by_warehouse"),
            {"product": str(self.product.pk)},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["product"]["unit_code"], "UND")
        self.assertEqual(len(data["warehouses"]), 2)
        stock_by_name = {item["warehouse"]: item["stock"] for item in data["warehouses"]}
        self.assertEqual(stock_by_name[self.warehouse.name], "12.500")
        self.assertEqual(stock_by_name[other_warehouse.name], "0")

    # ── Entry ─────────────────────────────────────────────────────────────────

    def test_entry_create_get(self):
        resp = self.client.get(reverse("inventory:entry_create"))
        self.assertEqual(resp.status_code, 200)

    def test_entry_create_saves_draft_without_changing_stock(self):
        resp = self._post_movement(reverse("inventory:entry_create"))
        self.assertRedirects(resp, reverse("inventory:movement_list"))
        self.assertFalse(StockByWarehouse.objects.filter(product=self.product, warehouse=self.warehouse).exists())
        self.assertEqual(Movement.objects.filter(type="ENTRY").count(), 1)

    def test_entry_creates_details(self):
        self._post_movement(reverse("inventory:entry_create"))
        mv = Movement.objects.get(type="ENTRY")
        self.assertEqual(mv.details.count(), 1)
        self.assertEqual(mv.details.first().quantity, Decimal("5"))

    # ── Exit ──────────────────────────────────────────────────────────────────

    def test_exit_create_decreases_stock(self):
        # First create stock
        self._post_movement(reverse("inventory:entry_create"))
        entry = Movement.objects.get(type="ENTRY")
        self.client.post(reverse("inventory:movement_confirm", args=[entry.pk]))
        resp = self._post_movement(
            reverse("inventory:exit_create"),
            {"lines-0-quantity": "3"},
        )
        self.assertRedirects(resp, reverse("inventory:movement_list"))
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal("5"))

        exit_movement = Movement.objects.get(type="EXIT")
        self.client.post(reverse("inventory:movement_confirm", args=[exit_movement.pk]))
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, Decimal("2"))  # 5 - 3

    # ── Transfer ──────────────────────────────────────────────────────────────

    def test_transfer_create(self):
        wh2 = Warehouse.objects.create(store=self.store, name="Almacén B")
        # Add stock to wh1 first
        self._post_movement(reverse("inventory:entry_create"))
        entry = Movement.objects.get(type="ENTRY")
        self.client.post(reverse("inventory:movement_confirm", args=[entry.pk]))

        now = timezone.now().strftime("%Y-%m-%dT%H:%M")
        resp = self.client.post(reverse("inventory:transfer_create"), {
            "date": now,
            "warehouse_origin": str(self.warehouse.pk),
            "warehouse_dest": str(wh2.pk),
            "reason": "Traslado",
            "reference_doc": "",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.pk),
            "lines-0-quantity": "2",
            "lines-0-unit_price": "0",
        })
        self.assertRedirects(resp, reverse("inventory:movement_list"))
        stock_a = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock_a.quantity, Decimal("5"))
        self.assertFalse(StockByWarehouse.objects.filter(product=self.product, warehouse=wh2).exists())

        transfer = Movement.objects.get(type="TRANSFER")
        self.client.post(reverse("inventory:movement_confirm", args=[transfer.pk]))
        stock_a.refresh_from_db()
        stock_b = StockByWarehouse.objects.get(product=self.product, warehouse=wh2)
        self.assertEqual(stock_a.quantity, Decimal("3"))  # 5 - 2
        self.assertEqual(stock_b.quantity, Decimal("2"))

    # ── Adjustment ─────────────────────────────────────────────────────────

    def test_adjustment_accepts_zero_physical_quantity(self):
        self._post_movement(reverse("inventory:entry_create"))
        entry = Movement.objects.get(type="ENTRY")
        self.client.post(reverse("inventory:movement_confirm", args=[entry.pk]))

        resp = self._post_movement(
            reverse("inventory:adjustment_create"),
            {"lines-0-quantity": "0"},
        )

        self.assertRedirects(resp, reverse("inventory:movement_list"))
        stock = StockByWarehouse.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal("5"))

        adjustment = Movement.objects.get(type="ADJUSTMENT")
        self.client.post(reverse("inventory:movement_confirm", args=[adjustment.pk]))
        stock.refresh_from_db()
        adjustment.refresh_from_db()
        self.assertEqual(stock.quantity, Decimal("0"))
        detail = adjustment.details.get()
        self.assertEqual(detail.physical_quantity, Decimal("0"))
        self.assertEqual(detail.quantity, Decimal("-5"))

    # ── Stock report ──────────────────────────────────────────────────────────

    def test_stock_report_ok(self):
        self._post_movement(reverse("inventory:entry_create"))
        movement = Movement.objects.get(type="ENTRY")
        self.client.post(reverse("inventory:movement_confirm", args=[movement.pk]))
        resp = self.client.get(reverse("inventory:stock_report"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Producto Test")

    def test_stock_report_orders_by_quantity_and_preserves_filters(self):
        second_product = Product.objects.create(
            company=self.company,
            name="Producto Segundo", sku="TEST-02", unit=self.unit,
            price_purchase=Decimal("5"), price_sale=Decimal("8"),
        )
        StockByWarehouse.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=Decimal("2")
        )
        StockByWarehouse.objects.create(
            product=second_product, warehouse=self.warehouse, quantity=Decimal("9")
        )

        response = self.client.get(
            reverse("inventory:stock_report"),
            {
                "warehouse": str(self.warehouse.pk),
                "q": "TEST",
                "sort": "quantity",
                "dir": "desc",
            },
        )

        self.assertEqual(
            [stock.product_id for stock in response.context["stocks"]],
            [second_product.pk, self.product.pk],
        )
        self.assertContains(response, "sort=quantity")
        self.assertContains(response, "dir=asc")
        self.assertContains(response, f"warehouse={self.warehouse.pk}")
        self.assertContains(response, "q=TEST")

    def test_stock_report_filters_by_category_and_brand_and_links_sku(self):
        from apps.inventory.models import Brand, Category

        category = Category.objects.create(
            company=self.company, code="TOOLS", name="Herramientas"
        )
        brand = Brand.objects.create(company=self.company, name="Marca Uno")
        self.product.category = category
        self.product.brand = brand
        self.product.save(update_fields=("category", "brand"))
        other_product = Product.objects.create(
            company=self.company,
            name="Producto Excluido", sku="OTHER-01", unit=self.unit,
            price_purchase=Decimal("5"), price_sale=Decimal("8"),
        )
        StockByWarehouse.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=Decimal("3")
        )
        StockByWarehouse.objects.create(
            product=other_product, warehouse=self.warehouse, quantity=Decimal("4")
        )

        response = self.client.get(reverse("inventory:stock_report"), {
            "category": str(category.pk),
            "brand": str(brand.pk),
        })

        self.assertEqual([stock.product_id for stock in response.context["stocks"]], [self.product.pk])
        self.assertContains(response, "Herramientas")
        self.assertContains(response, "Marca Uno")
        self.assertContains(
            response,
            f'<a href="{reverse("inventory:product_update", args=[self.product.pk])}" '
            f'title="Editar producto {self.product.sku}">{self.product.sku}</a>',
            html=True,
        )

    def test_product_list_sku_links_to_product_edit(self):
        response = self.client.get(reverse("inventory:product_list"))

        self.assertContains(
            response,
            f'<a href="{reverse("inventory:product_update", args=[self.product.pk])}" '
            f'title="Editar producto {self.product.sku}">{self.product.sku}</a>',
            html=True,
        )

    # ── Movement detail ───────────────────────────────────────────────────────

    def test_movement_detail_ok(self):
        self._post_movement(reverse("inventory:entry_create"))
        mv = Movement.objects.first()
        resp = self.client.get(reverse("inventory:movement_detail", args=[mv.pk]))
        self.assertEqual(resp.status_code, 200)

    # ── Movement edit/delete ─────────────────────────────────────────────────

    def test_movement_edit_recalculates_stock(self):
        self._post_movement(reverse("inventory:entry_create"))
        movement = Movement.objects.get(type="ENTRY")

        resp = self.client.post(reverse("inventory:movement_edit", args=[movement.pk]), {
            "date": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "warehouse": str(self.warehouse.pk),
            "reason": "Ajuste de entrada",
            "reference_doc": "",
            "supplier": "",
            "customer": "",
            "carrier": "",
            "document_type": "",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "1",
            "lines-MIN_NUM_FORMS": "1",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.pk),
            "lines-0-quantity": "3",
            "lines-0-unit_price": "10",
        })

        self.assertRedirects(resp, reverse("inventory:movement_list"))
        self.assertFalse(StockByWarehouse.objects.filter(product=self.product, warehouse=self.warehouse).exists())
        movement.refresh_from_db()
        self.assertEqual(movement.details.get().quantity, Decimal("3"))

    def test_movement_update_alert_includes_detail_link(self):
        self._post_movement(reverse("inventory:entry_create"))
        movement = Movement.objects.get(type="ENTRY")

        response = self.client.post(
            reverse("inventory:movement_confirm", args=[movement.pk]), follow=True
        )

        self.assertContains(response, "Movimiento aplicado al stock:")
        self.assertContains(response, reverse("inventory:movement_detail", args=[movement.pk]))

    def test_movement_delete_reverts_stock(self):
        self._post_movement(reverse("inventory:entry_create"))
        movement = Movement.objects.get(type="ENTRY")

        resp = self.client.post(reverse("inventory:movement_delete", args=[movement.pk]))
        self.assertRedirects(resp, reverse("inventory:movement_list"))

        self.assertFalse(StockByWarehouse.objects.filter(product=self.product, warehouse=self.warehouse).exists())
        self.assertFalse(Movement.objects.filter(pk=movement.pk).exists())

    def test_operation_code_links_to_edit_for_draft_and_detail_when_applied(self):
        self._post_movement(reverse("inventory:entry_create"))
        movement = Movement.objects.get(type="ENTRY")

        response = self.client.get(reverse("inventory:movement_list"))
        self.assertContains(
            response,
            f'<a href="{reverse("inventory:movement_edit", args=[movement.pk])}" title="Editar borrador">{movement.operation_code}</a>',
            html=True,
        )

        self.client.post(reverse("inventory:movement_confirm", args=[movement.pk]))
        response = self.client.get(reverse("inventory:movement_list"))
        self.assertContains(
            response,
            f'<a href="{reverse("inventory:movement_detail", args=[movement.pk])}" title="Ver detalle">{movement.operation_code}</a>',
            html=True,
        )

    def test_movement_list_can_search_by_operation_code(self):
        self._post_movement(reverse("inventory:entry_create"))
        movement = Movement.objects.get(type="ENTRY")

        response = self.client.get(reverse("inventory:movement_list"), {"q": movement.operation_code})

        self.assertContains(response, movement.operation_code)
        self.assertEqual(response.context["page_obj"].paginator.count, 1)

    def test_movement_list_orders_by_code_descending(self):
        self._post_movement(reverse("inventory:entry_create"))
        first = Movement.objects.get(type="ENTRY")
        self._post_movement(reverse("inventory:entry_create"))
        second = Movement.objects.order_by("-operation_number").first()

        response = self.client.get(
            reverse("inventory:movement_list"),
            {"sort": "code", "dir": "desc"},
        )

        self.assertEqual(list(response.context["page_obj"]), [second, first])
        self.assertEqual(
            response.context["table_sort"],
            {"key": "code", "direction": "desc"},
        )

    def test_movement_edit_shows_operation_code_in_breadcrumb_and_header(self):
        self._post_movement(reverse("inventory:entry_create"))
        movement = Movement.objects.get(type="ENTRY")

        response = self.client.get(reverse("inventory:movement_edit", args=[movement.pk]))

        self.assertEqual(response.status_code, 200)
        detail_url = reverse("inventory:movement_detail", args=[movement.pk])
        self.assertContains(
            response,
            f'<a href="{detail_url}">{movement.operation_code}</a>',
            html=True,
        )
        self.assertContains(
            response,
            f'<a href="{detail_url}" class="badge bg-azure-lt text-azure ms-2" '
            f'title="Ver detalle del movimiento">{movement.operation_code}</a>',
            html=True,
        )
