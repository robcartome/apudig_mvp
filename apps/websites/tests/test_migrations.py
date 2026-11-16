from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.companies.models import Company, Store
from apps.inventory.models import Movement, Product, StockByWarehouse, Unit, Warehouse
from apps.partners.models import Customer
from apps.sales.models import SalesQuotation
from apps.websites.schema_audit import audit_website_schema


class SchemaAuditTest(TestCase):
    def test_current_applied_schema_matches_history(self):
        report = audit_website_schema(connection)
        self.assertTrue(report["compatible"], report["issues"])
        self.assertIn("website_domains", report["schema"])

    def test_unrecorded_tables_fail_closed_without_modification(self):
        tables = connection.introspection.table_names()
        with patch.object(connection.introspection, "table_names", return_value=tables + ["website_unrecorded"]):
            with self.assertRaises(CommandError):
                call_command("audit_website_schema", stdout=StringIO())
        self.assertEqual(connection.introspection.table_names(), tables)

    def test_unknown_applied_migration_reported(self):
        # The simulated divergent recorder entry is rolled back with this test.
        MigrationRecorder(connection).record_applied("websites", "9999_unknown")
        report = audit_website_schema(connection)
        self.assertFalse(report["compatible"])
        self.assertIn("9999_unknown", str(report["issues"]))

    def test_missing_constraint_reported(self):
        original = connection.introspection.get_constraints

        def omit_constraint(cursor, table):
            constraints = original(cursor, table)
            if table == "website_domains":
                constraints.pop("website_verified_domain_evidence", None)
            return constraints

        with patch.object(connection.introspection, "get_constraints", side_effect=omit_constraint):
            self.assertFalse(audit_website_schema(connection)["compatible"])


class WebsiteMigrationTest(TransactionTestCase):
    """Run real migration upgrades in the test DB, never the configured ERP DB."""

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_previous_migration_names_are_recognized_without_reapplying_schema(self):
        recorder = MigrationRecorder(connection)
        executor = MigrationExecutor(connection)
        renamed = [
            ("websites", "0003_website_pages_sections_and_revisions"),
            ("websites", "0004_website_theme_media_menus_and_seo"),
        ]
        # Simulate an installation migrated before the descriptive rename:
        # keep the original recorder entries and physical schema intact.
        for node in renamed:
            for previous in executor.loader.disk_migrations[node].replaces:
                self.assertIn(previous, recorder.applied_migrations())
            recorder.record_unapplied(*node)
        executor = MigrationExecutor(connection)
        executor.loader.check_consistent_history(connection)
        self.assertEqual(executor.migration_plan(executor.loader.graph.leaf_nodes()), [])
        report = audit_website_schema(connection)
        self.assertTrue(report["compatible"], report["issues"])
        executor.migrate(executor.loader.graph.leaf_nodes())
        for node in renamed:
            self.assertIn(node, recorder.applied_migrations())

    def test_partially_applied_previous_chain_can_upgrade(self):
        target = ("websites", "0003_website_pages_sections_and_revisions")
        executor = MigrationExecutor(connection)
        executor.migrate([target])
        recorder = MigrationRecorder(connection)
        recorder.record_unapplied(*target)
        executor = MigrationExecutor(connection)
        executor.loader.check_consistent_history(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        self.assertNotIn(target, [(migration.app_label, migration.name) for migration, _ in plan])
        self.assertIn(
            ("websites", "0004_website_theme_media_menus_and_seo"),
            [(migration.app_label, migration.name) for migration, _ in plan],
        )
        executor.migrate(executor.loader.graph.leaf_nodes())
        report = audit_website_schema(connection)
        self.assertTrue(report["compatible"], report["issues"])

    def test_editorial_extension_preserves_existing_snapshots_without_publishing(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("websites", "0007_website_editorial_revision_and_more")])
        executor = MigrationExecutor(connection)
        nodes = sorted(set(executor.loader.applied_migrations).intersection(executor.loader.graph.nodes))
        state = executor.loader.project_state(nodes=nodes).apps
        LegacyWebsite = state.get_model("websites", "Website")
        LegacyPage = state.get_model("websites", "WebsitePage")
        LegacyRevision = state.get_model("websites", "WebsitePageRevision")
        company = Company.objects.create(name="Existing CMS", ruc="20999999203")
        website = LegacyWebsite.objects.create(company_id=company.pk, name="Existing web", slug="existing-web")
        page = LegacyPage.objects.create(website=website, page_type="HOME", slug="home", title="Existing home")
        snapshot = {"page": {"title": "Historical title"}, "sections": [{"type": "hero.v1", "title": "Historical banner"}]}
        revision = LegacyRevision.objects.create(page=page, version=1, snapshot=snapshot)
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        from apps.websites.models import Website, WebsitePageRevision
        saved = WebsitePageRevision.objects.get(pk=revision.pk)
        self.assertEqual(saved.snapshot, snapshot)
        self.assertEqual(saved.operation, "BASELINE")
        self.assertIsNone(saved.editorial_revision)
        self.assertIsNone(Website.objects.get(pk=website.pk).published_revision_id)
        self.assertTrue(audit_website_schema(connection)["compatible"])

    def test_new_website_chain_preserves_existing_erp_records(self):
        MigrationExecutor(connection).migrate([("websites", None)])
        before = audit_website_schema(connection)
        self.assertTrue(before["compatible"])
        self.assertEqual(before["website_migrations"], [])
        company = Company.objects.create(name="Migration A", ruc="20999999201")
        store = Store.objects.create(company=company, name="Existing store")
        unit = Unit.objects.create(code="B1", name="Unit")
        product = Product.objects.create(company=company, name="Existing product", sku="B1-existing", unit=unit, price_sale=Decimal("25.00"), price_purchase=Decimal("10.00"))
        warehouse = Warehouse.objects.create(store=store, name="Existing warehouse")
        stock = StockByWarehouse.objects.create(product=product, warehouse=warehouse, quantity=Decimal("7.500"))
        customer = Customer.objects.create(company=company, document_type="0", legal_name="Existing customer")
        quotation = SalesQuotation.objects.create(store=store, customer=customer, customer_document_type="0", customer_document_number="", customer_legal_name=customer.legal_name, issue_date=timezone.localdate(), total=Decimal("25.00"))
        movement = Movement(id=None, operation_year=2026, type="ENTRY", store=store, warehouse=warehouse, date=timezone.now(), status="DRAFT")
        # Avoid operational stock effects: this is pre-existing schema data.
        Movement.objects.bulk_create([movement])
        originals = {
            model: list(model.objects.values().order_by("pk"))
            for model in (Company, Store, Product, Warehouse, StockByWarehouse, Customer, SalesQuotation, Movement)
        }
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        for model, rows in originals.items():
            self.assertEqual(list(model.objects.values().order_by("pk")), rows, model.__name__)
        self.assertTrue(audit_website_schema(connection)["compatible"])
        self.assertTrue(StockByWarehouse.objects.filter(pk=stock.pk, quantity="7.500").exists())
        self.assertTrue(SalesQuotation.objects.filter(pk=quotation.pk, total="25.00").exists())

    def test_invalid_historical_domains_abort_upgrade_without_rewriting_data(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("websites", "0006_website_template")])
        # Include all other applied ERP nodes: a website-only projection can
        # leave the legacy billing/sales consolidation at an intermediate state.
        executor = MigrationExecutor(connection)
        nodes = sorted(set(executor.loader.applied_migrations).intersection(executor.loader.graph.nodes))
        state = executor.loader.project_state(nodes=nodes).apps
        HistoricalWebsite = state.get_model("websites", "Website")
        HistoricalDomain = state.get_model("websites", "WebsiteDomain")
        company = Company.objects.create(name="History A", ruc="20999999202")
        website = HistoricalWebsite.objects.create(company_id=company.pk, name="History", slug="history")
        domain = HistoricalDomain.objects.create(website=website, hostname="UNNORMALIZED.example.com", status="ACTIVE")
        try:
            with self.assertRaisesRegex(RuntimeError, "Dominios históricos incompatibles"):
                executor = MigrationExecutor(connection)
                executor.migrate(executor.loader.graph.leaf_nodes())
            self.assertTrue(HistoricalDomain.objects.filter(pk=domain.pk, hostname="UNNORMALIZED.example.com", verified_at__isnull=True).exists())
            applied = MigrationRecorder(connection).applied_migrations()
            self.assertNotIn(("websites", "0007_website_editorial_revision_and_more"), applied)
        finally:
            # Test fixture cleanup, not an automatic repair of application data.
            HistoricalDomain.objects.filter(pk=domain.pk).delete()
