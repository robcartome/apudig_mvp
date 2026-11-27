from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from apps.companies.models import Company, Store
from apps.inventory.models import PriceList, Product, ProductPrice, Unit
from apps.users.models import UserStore


class PriceReportTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Empresa reporte", ruc="20123456789")
        self.store = Store.objects.create(company=self.company, name="Principal")
        self.user = get_user_model().objects.create_user(
            email="reporte@example.com", password="test", is_superuser=True,
        )
        UserStore.objects.create(user=self.user, store=self.store, role="ADMIN")
        self.client.force_login(self.user)
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()
        unit = Unit.objects.create(code="URP", name="Unidad reporte")
        self.product = Product.objects.create(
            company=self.company, unit=unit, name="=Producto", sku="RP-01",
            price_purchase=Decimal("5"), price_sale=Decimal("10"),
        )
        self.distributor = PriceList.objects.create(company=self.company, name="DISTRIBUIDOR")
        self.wholesale = PriceList.objects.create(company=self.company, name="MAYORISTA")
        ProductPrice.objects.create(product=self.product, price_list=self.wholesale, amount=Decimal("8"))
        ProductPrice.objects.create(product=self.product, price_list=self.distributor, amount=Decimal("7"))

    def workbook(self, **params):
        response = self.client.get(reverse("inventory:price_report"), {"format": "xlsx", **params})
        self.assertEqual(response.status_code, 200)
        return load_workbook(BytesIO(response.content)).active

    def test_report_is_in_reports_menu_and_offers_column_controls(self):
        response = self.client.get(reverse("inventory:price_report"))
        self.assertContains(response, 'id="column-options"', html=False)
        self.assertContains(response, 'class="collapse show" id="sidebar-reports"', html=False)
        self.assertContains(response, 'class="collapse " id="sidebar-products"', html=False)

    def test_sku_links_to_the_product_edit_form(self):
        response = self.client.get(reverse("inventory:price_report"))
        edit_url = reverse("inventory:product_update", args=[self.product.pk])
        self.assertContains(response, f'href="{edit_url}"', html=False)
        self.assertEqual(self.client.get(edit_url).status_code, 200)

    def test_excel_preserves_requested_order_and_values(self):
        sheet = self.workbook(cols=f"venta,{self.wholesale.pk},compra,{self.distributor.pk}")
        self.assertEqual([cell.value for cell in sheet[1]],
                         ["SKU", "Nombre", "Precio Venta", "MAYORISTA", "Precio Compra", "DISTRIBUIDOR"])
        self.assertEqual([cell.value for cell in sheet[2]], ["RP-01", "=Producto", 10, 8, 5, 7])
        self.assertEqual(sheet["B2"].data_type, "s")

    def test_excel_with_no_price_columns_has_only_identifiers(self):
        sheet = self.workbook(cols="")
        self.assertEqual([cell.value for cell in sheet[1]], ["SKU", "Nombre"])

    def test_export_uses_search_filter_and_is_not_limited_to_screen_page(self):
        Product.objects.bulk_create([
            Product(company=self.company, unit=self.product.unit, name=f"Lote {index}",
                    sku=f"LOTE-{index:03d}", price_purchase=1, price_sale=2)
            for index in range(55)
        ])
        sheet = self.workbook(q="LOTE-", page="2", cols="compra")
        self.assertEqual(sheet.max_row, 56)
        self.assertEqual([cell.value for cell in sheet[1]], ["SKU", "Nombre", "Precio Compra"])

    def test_excel_ignores_duplicates_and_other_company_columns(self):
        other = Company.objects.create(name="Otra empresa", ruc="20987654321")
        foreign = PriceList.objects.create(company=other, name="OTRA")
        sheet = self.workbook(cols=f"{foreign.pk},venta,venta,{self.wholesale.pk}")
        self.assertEqual([cell.value for cell in sheet[1]], ["SKU", "Nombre", "Precio Venta", "MAYORISTA"])
