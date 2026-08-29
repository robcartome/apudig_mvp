from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.companies.models import Company, Store, UserCompanyAccess
from apps.inventory.models import Product, ProductSupplier, StockByWarehouse, Unit, Warehouse
from apps.inventory.selectors import search_products
from apps.partners.models import Supplier
from apps.users.models import User


class ProductSupplierTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Empresa A", ruc="20900000001")
        self.other_company = Company.objects.create(name="Empresa B", ruc="20900000002")
        self.unit = Unit.objects.create(code="UND", name="Unidad")
        self.product = Product.objects.create(
            company=self.company, name="Válvula", sku="VAL-01", unit=self.unit
        )
        self.other_product = Product.objects.create(
            company=self.company, name="Tubo", sku="TUB-01", unit=self.unit
        )
        self.foreign_product = Product.objects.create(
            company=self.other_company, name="Producto externo", sku="EXT-01", unit=self.unit
        )
        self.supplier_a = Supplier.objects.create(
            company=self.company, name="Poelsan", document_number="20100000001"
        )
        self.supplier_b = Supplier.objects.create(
            company=self.company, name="Proveedor B", document_number="20100000002"
        )
        self.foreign_supplier = Supplier.objects.create(
            company=self.other_company, name="Proveedor externo", document_number="20200000001"
        )

    def test_create_relation_and_product_with_multiple_suppliers(self):
        first = ProductSupplier.objects.create(
            product=self.product, supplier=self.supplier_a,
            supplier_code=" P-010203 ", purchase_price=Decimal("8.20"),
        )
        ProductSupplier.objects.create(product=self.product, supplier=self.supplier_b)

        self.assertEqual(first.company, self.company)
        self.assertEqual(first.supplier_code, "P-010203")
        self.assertEqual(self.product.supplier_relations.count(), 2)

    def test_two_products_can_use_different_suppliers(self):
        ProductSupplier.objects.create(product=self.product, supplier=self.supplier_a)
        ProductSupplier.objects.create(product=self.other_product, supplier=self.supplier_b)
        self.assertEqual(ProductSupplier.objects.count(), 2)

    def test_rejects_product_and_supplier_from_different_companies(self):
        relation = ProductSupplier(product=self.product, supplier=self.foreign_supplier)
        with self.assertRaises(ValidationError):
            relation.save()

    def test_rejects_duplicate_product_supplier(self):
        ProductSupplier.objects.create(product=self.product, supplier=self.supplier_a)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductSupplier.objects.create(product=self.product, supplier=self.supplier_a)

    def test_rejects_duplicate_nonempty_code_for_same_supplier(self):
        ProductSupplier.objects.create(
            product=self.product, supplier=self.supplier_a, supplier_code="ABC"
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductSupplier.objects.create(
                product=self.other_product, supplier=self.supplier_a, supplier_code="ABC"
            )

    def test_allows_same_code_for_different_suppliers(self):
        ProductSupplier.objects.create(
            product=self.product, supplier=self.supplier_a, supplier_code="ABC"
        )
        ProductSupplier.objects.create(
            product=self.other_product, supplier=self.supplier_b, supplier_code="ABC"
        )
        self.assertEqual(ProductSupplier.objects.filter(supplier_code="ABC").count(), 2)

    def test_allows_multiple_empty_codes(self):
        ProductSupplier.objects.create(product=self.product, supplier=self.supplier_a)
        ProductSupplier.objects.create(product=self.other_product, supplier=self.supplier_a)
        self.assertEqual(ProductSupplier.objects.filter(supplier_code="").count(), 2)

    def test_rejects_more_than_one_preferred_supplier_per_product(self):
        ProductSupplier.objects.create(
            product=self.product, supplier=self.supplier_a, is_preferred=True
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductSupplier.objects.create(
                product=self.product, supplier=self.supplier_b, is_preferred=True
            )

    def test_inactive_relation_cannot_be_preferred_at_model_or_database_level(self):
        with self.assertRaises(ValidationError):
            ProductSupplier.objects.create(
                product=self.product, supplier=self.supplier_a,
                active=False, is_preferred=True,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductSupplier.objects.bulk_create([
                ProductSupplier(
                    company=self.company, product=self.product, supplier=self.supplier_a,
                    active=False, is_preferred=True,
                )
            ])

    def test_supplier_code_is_stripped_before_form_validation_and_save(self):
        first = ProductSupplier.objects.create(
            product=self.product, supplier=self.supplier_a, supplier_code=" CODE "
        )
        self.assertEqual(first.supplier_code, "CODE")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductSupplier.objects.create(
                product=self.other_product, supplier=self.supplier_a, supplier_code=" CODE "
            )

    def test_search_products_by_supplier_code_without_duplicates(self):
        ProductSupplier.objects.create(
            product=self.product, supplier=self.supplier_a, supplier_code="P-010203"
        )
        ProductSupplier.objects.create(
            product=self.product, supplier=self.supplier_b,
            supplier_code="OTHER", supplier_product_name="VALV BOLA PVC",
        )
        self.assertEqual(list(search_products("P-010203", self.company.pk)), [self.product])
        self.assertEqual(list(search_products("VALV BOLA", self.company.pk)), [self.product])

    def test_search_by_code_and_selected_supplier(self):
        ProductSupplier.objects.create(
            product=self.product, supplier=self.supplier_a, supplier_code="SHARED"
        )
        ProductSupplier.objects.create(
            product=self.other_product, supplier=self.supplier_b, supplier_code="SHARED"
        )
        results = search_products("SHARED", self.company.pk, supplier_id=self.supplier_a.pk)
        self.assertEqual(list(results), [self.product])

    def test_selected_supplier_does_not_match_another_suppliers_code(self):
        ProductSupplier.objects.create(
            product=self.product, supplier=self.supplier_a, supplier_code="POELSAN"
        )
        ProductSupplier.objects.create(
            product=self.product, supplier=self.supplier_b, supplier_code="ONLY-B"
        )
        results = search_products("ONLY-B", self.company.pk, supplier_id=self.supplier_a.pk)
        self.assertFalse(results.exists())

    def test_selected_supplier_does_not_hide_product_found_by_internal_sku(self):
        results = search_products(
            self.other_product.sku, self.company.pk, supplier_id=self.supplier_a.pk
        )
        self.assertEqual(list(results), [self.other_product])

    def test_inactive_relation_is_not_searchable_by_supplier_catalog_fields(self):
        ProductSupplier.objects.create(
            product=self.product, supplier=self.supplier_a,
            supplier_code="INACTIVE-CODE", active=False,
        )
        self.assertFalse(search_products("INACTIVE-CODE", self.company.pk).exists())

    def test_search_never_returns_another_company(self):
        ProductSupplier.objects.create(
            product=self.foreign_product, supplier=self.foreign_supplier, supplier_code="FOREIGN"
        )
        self.assertFalse(search_products("FOREIGN", self.company.pk).exists())


class ProductSupplierViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="supplier@demo.com", password="testpass")
        self.company = Company.objects.create(name="Empresa UI", ruc="20900000003")
        self.store = Store.objects.create(company=self.company, name="Principal")
        UserCompanyAccess.objects.create(
            user=self.user, company=self.company, store=self.store, is_default=True
        )
        self.unit = Unit.objects.create(code="NIU", name="Unidad")
        self.product = Product.objects.create(
            company=self.company, name="Válvula", sku="VAL-UI", unit=self.unit,
            price_purchase=Decimal("8.00"), price_sale=Decimal("12.00"),
        )
        self.supplier = Supplier.objects.create(
            company=self.company, name="Poelsan", document_number="20100000003"
        )
        self.second_supplier = Supplier.objects.create(
            company=self.company, name="Proveedor B", document_number="20100000004"
        )
        self.foreign_company = Company.objects.create(name="Empresa externa", ruc="20900000005")
        self.foreign_supplier = Supplier.objects.create(
            company=self.foreign_company, name="Proveedor externo", document_number="20100000005"
        )
        self.relation = ProductSupplier.objects.create(
            product=self.product, supplier=self.supplier, supplier_code="OLD"
        )
        self.client.login(username="supplier@demo.com", password="testpass")
        session = self.client.session
        session["active_company_id"] = str(self.company.pk)
        session["active_store_id"] = str(self.store.pk)
        session.save()

    def _product_payload(self, **overrides):
        data = {
            "name": self.product.name,
            "sku": self.product.sku,
            "barcode": "",
            "description": "",
            "model": "",
            "price_purchase": "8.00",
            "price_sale": "12.00",
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

    def test_product_update_keeps_and_updates_supplier_relation(self):
        response = self.client.post(reverse("inventory:product_update", args=[self.product.pk]), self._product_payload(**{
            "suppliers-TOTAL_FORMS": "1",
            "suppliers-INITIAL_FORMS": "1",
            "suppliers-MIN_NUM_FORMS": "0",
            "suppliers-MAX_NUM_FORMS": "1000",
            "suppliers-0-id": str(self.relation.pk),
            "suppliers-0-supplier": str(self.supplier.pk),
            "suppliers-0-supplier_code": "NEW-CODE",
            "suppliers-0-supplier_product_name": "Nombre Poelsan",
            "suppliers-0-supplier_description": "",
            "suppliers-0-purchase_price": "8.35",
            "suppliers-0-is_preferred": "on",
            "suppliers-0-active": "on",
        }))

        self.assertRedirects(response, reverse("inventory:product_list"))
        self.relation.refresh_from_db()
        self.assertEqual(self.relation.supplier_code, "NEW-CODE")
        self.assertEqual(self.relation.purchase_price, Decimal("8.350000"))
        self.assertTrue(self.relation.is_preferred)

    def test_product_update_success_alert_includes_link_to_product(self):
        response = self.client.post(
            reverse("inventory:product_update", args=[self.product.pk]),
            self._product_payload(),
            follow=True,
        )

        self.assertContains(response, "Producto actualizado:")
        self.assertContains(response, self.product.sku)
        self.assertContains(response, self.product.name)
        self.assertContains(
            response, reverse("inventory:product_update", args=[self.product.pk])
        )

    def test_product_delete_success_alert_includes_product_identity(self):
        product_sku = self.product.sku
        product_name = self.product.name
        response = self.client.post(
            reverse("inventory:product_delete", args=[self.product.pk]), follow=True
        )

        self.assertContains(response, "Producto eliminado:")
        self.assertContains(response, product_sku)
        self.assertContains(response, product_name)
        self.assertFalse(Product.objects.filter(pk=self.product.pk).exists())

    def test_product_create_saves_multiple_supplier_relations_atomically(self):
        response = self.client.post(reverse("inventory:product_create"), self._product_payload(**{
            "name": "Producto nuevo",
            "sku": "NEW-MULTI",
            "suppliers-TOTAL_FORMS": "2",
            "suppliers-INITIAL_FORMS": "0",
            "suppliers-MIN_NUM_FORMS": "0",
            "suppliers-MAX_NUM_FORMS": "1000",
            "suppliers-0-supplier": str(self.supplier.pk),
            "suppliers-0-supplier_code": "P-1",
            "suppliers-0-supplier_product_name": "",
            "suppliers-0-supplier_description": "",
            "suppliers-0-purchase_price": "8.10",
            "suppliers-0-is_preferred": "on",
            "suppliers-0-active": "on",
            "suppliers-1-supplier": str(self.second_supplier.pk),
            "suppliers-1-supplier_code": "B-1",
            "suppliers-1-supplier_product_name": "",
            "suppliers-1-supplier_description": "",
            "suppliers-1-purchase_price": "8.20",
            "suppliers-1-active": "on",
        }))
        self.assertRedirects(response, reverse("inventory:product_list"))
        created = Product.objects.get(sku="NEW-MULTI")
        self.assertEqual(created.supplier_relations.count(), 2)

    def test_product_update_can_delete_supplier_relation(self):
        response = self.client.post(reverse("inventory:product_update", args=[self.product.pk]), self._product_payload(**{
            "suppliers-TOTAL_FORMS": "1",
            "suppliers-INITIAL_FORMS": "1",
            "suppliers-MIN_NUM_FORMS": "0",
            "suppliers-MAX_NUM_FORMS": "1000",
            "suppliers-0-id": str(self.relation.pk),
            "suppliers-0-supplier": str(self.supplier.pk),
            "suppliers-0-supplier_code": self.relation.supplier_code,
            "suppliers-0-supplier_product_name": "",
            "suppliers-0-supplier_description": "",
            "suppliers-0-purchase_price": "",
            "suppliers-0-active": "on",
            "suppliers-0-DELETE": "on",
        }))
        self.assertRedirects(response, reverse("inventory:product_list"))
        self.assertFalse(ProductSupplier.objects.filter(pk=self.relation.pk).exists())

    def test_invalid_supplier_formset_does_not_partially_update_product(self):
        response = self.client.post(reverse("inventory:product_update", args=[self.product.pk]), self._product_payload(**{
            "name": "No debe persistir",
            "suppliers-TOTAL_FORMS": "2",
            "suppliers-INITIAL_FORMS": "1",
            "suppliers-MIN_NUM_FORMS": "0",
            "suppliers-MAX_NUM_FORMS": "1000",
            "suppliers-0-id": str(self.relation.pk),
            "suppliers-0-supplier": str(self.supplier.pk),
            "suppliers-0-supplier_code": "OLD",
            "suppliers-0-supplier_product_name": "",
            "suppliers-0-supplier_description": "",
            "suppliers-0-purchase_price": "",
            "suppliers-0-is_preferred": "on",
            "suppliers-0-active": "on",
            "suppliers-1-supplier": str(self.second_supplier.pk),
            "suppliers-1-supplier_code": "B-2",
            "suppliers-1-supplier_product_name": "",
            "suppliers-1-supplier_description": "",
            "suppliers-1-purchase_price": "",
            "suppliers-1-is_preferred": "on",
            "suppliers-1-active": "on",
        }))
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Válvula")
        self.assertEqual(self.product.supplier_relations.count(), 1)

    def test_legacy_post_without_supplier_management_form_preserves_relations(self):
        response = self.client.post(
            reverse("inventory:product_update", args=[self.product.pk]),
            self._product_payload(name="Nombre actualizado"),
        )
        self.assertRedirects(response, reverse("inventory:product_list"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Nombre actualizado")
        self.assertTrue(ProductSupplier.objects.filter(pk=self.relation.pk).exists())

    def test_manipulated_post_cannot_assign_supplier_from_another_company(self):
        response = self.client.post(reverse("inventory:product_update", args=[self.product.pk]), self._product_payload(**{
            "name": "No debe persistir",
            "suppliers-TOTAL_FORMS": "1",
            "suppliers-INITIAL_FORMS": "1",
            "suppliers-MIN_NUM_FORMS": "0",
            "suppliers-MAX_NUM_FORMS": "1000",
            "suppliers-0-id": str(self.relation.pk),
            "suppliers-0-supplier": str(self.foreign_supplier.pk),
            "suppliers-0-supplier_code": "FOREIGN",
            "suppliers-0-supplier_product_name": "",
            "suppliers-0-supplier_description": "",
            "suppliers-0-purchase_price": "",
            "suppliers-0-active": "on",
        }))
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.relation.refresh_from_db()
        self.assertEqual(self.product.name, "Válvula")
        self.assertEqual(self.relation.supplier, self.supplier)

    def test_duplicate_supplier_code_returns_form_error_instead_of_500(self):
        other_product = Product.objects.create(
            company=self.company, name="Otro producto", sku="OTHER-DUP", unit=self.unit
        )
        ProductSupplier.objects.create(
            product=other_product, supplier=self.supplier, supplier_code="ADO112"
        )
        response = self.client.post(reverse("inventory:product_update", args=[self.product.pk]), self._product_payload(**{
            "name": "No debe persistir",
            "suppliers-TOTAL_FORMS": "1",
            "suppliers-INITIAL_FORMS": "1",
            "suppliers-MIN_NUM_FORMS": "0",
            "suppliers-MAX_NUM_FORMS": "1000",
            "suppliers-0-id": str(self.relation.pk),
            "suppliers-0-supplier": str(self.supplier.pk),
            "suppliers-0-supplier_code": " ADO112 ",
            "suppliers-0-supplier_product_name": "",
            "suppliers-0-supplier_description": "",
            "suppliers-0-purchase_price": "",
            "suppliers-0-active": "on",
        }))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "Este proveedor ya utiliza este código en otro producto."
        )
        self.assertContains(response, "Revisa la información:")
        self.product.refresh_from_db()
        self.relation.refresh_from_db()
        self.assertEqual(self.product.name, "Válvula")
        self.assertEqual(self.relation.supplier_code, "OLD")

    @patch(
        "apps.inventory.views.masters.ProductSupplierFormSet.save",
        side_effect=IntegrityError("simulated concurrent duplicate"),
    )
    def test_database_integrity_race_is_rendered_as_alert(self, _save_mock):
        response = self.client.post(reverse("inventory:product_update", args=[self.product.pk]), self._product_payload(**{
            "suppliers-TOTAL_FORMS": "1",
            "suppliers-INITIAL_FORMS": "1",
            "suppliers-MIN_NUM_FORMS": "0",
            "suppliers-MAX_NUM_FORMS": "1000",
            "suppliers-0-id": str(self.relation.pk),
            "suppliers-0-supplier": str(self.supplier.pk),
            "suppliers-0-supplier_code": "UNIQUE-CODE",
            "suppliers-0-supplier_product_name": "",
            "suppliers-0-supplier_description": "",
            "suppliers-0-purchase_price": "",
            "suppliers-0-active": "on",
        }))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No se pudieron guardar los proveedores")
        self.assertContains(response, "Error:")
        self.assertNotContains(response, "data-auto-dismiss")

    def test_product_search_api_uses_selected_supplier_and_company(self):
        response = self.client.get(reverse("inventory:api_product_search"), {
            "q": "OLD", "supplier": str(self.supplier.pk),
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()["products"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], str(self.product.pk))
        self.assertEqual(data[0]["supplier_code"], "OLD")

    def test_product_search_api_finds_unrelated_product_by_internal_sku(self):
        unrelated = Product.objects.create(
            company=self.company, name="Sin catálogo", sku="INTERNAL-ONLY", unit=self.unit
        )
        response = self.client.get(reverse("inventory:api_product_search"), {
            "q": "INTERNAL-ONLY", "supplier": str(self.supplier.pk),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()["products"]], [str(unrelated.pk)]
        )

    def test_stock_report_searches_by_active_supplier_code(self):
        warehouse = Warehouse.objects.create(store=self.store, name="Almacén")
        StockByWarehouse.objects.create(
            product=self.product, warehouse=warehouse, quantity=Decimal("3")
        )
        response = self.client.get(reverse("inventory:stock_report"), {"q": "OLD"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)

    def test_stock_report_ignores_inactive_supplier_code(self):
        self.relation.active = False
        self.relation.save(update_fields=["active", "updated_at"])
        warehouse = Warehouse.objects.create(store=self.store, name="Almacén")
        StockByWarehouse.objects.create(
            product=self.product, warehouse=warehouse, quantity=Decimal("3")
        )
        response = self.client.get(reverse("inventory:stock_report"), {"q": "OLD"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.product.name)
