from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0004_payment_method_means_of_payment"),
        ("partners", "0003_rename_corecustomer_to_customer"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE vouchers RENAME TO sales_documents",
                    reverse_sql="ALTER TABLE sales_documents RENAME TO vouchers",
                ),
                migrations.RunSQL(
                    sql="ALTER TABLE voucher_lines RENAME TO sales_document_lines",
                    reverse_sql="ALTER TABLE sales_document_lines RENAME TO voucher_lines",
                ),
                migrations.RunSQL(
                    sql="ALTER TABLE document_series RENAME COLUMN voucher_type TO document_type",
                    reverse_sql="ALTER TABLE document_series RENAME COLUMN document_type TO voucher_type",
                ),
                migrations.RunSQL(
                    sql="ALTER TABLE sales_documents RENAME COLUMN voucher_type TO document_type",
                    reverse_sql="ALTER TABLE sales_documents RENAME COLUMN document_type TO voucher_type",
                ),
                migrations.RunSQL(
                    sql="ALTER TABLE sales_documents RENAME COLUMN reference_voucher_id TO reference_document_id",
                    reverse_sql="ALTER TABLE sales_documents RENAME COLUMN reference_document_id TO reference_voucher_id",
                ),
                migrations.RunSQL(
                    sql="ALTER TABLE sales_document_lines RENAME COLUMN voucher_id TO sales_document_id",
                    reverse_sql="ALTER TABLE sales_document_lines RENAME COLUMN sales_document_id TO voucher_id",
                ),
            ],
            state_operations=[
                migrations.RenameModel(old_name="Voucher", new_name="SalesDocument"),
                migrations.RenameModel(old_name="VoucherLine", new_name="SalesDocumentLine"),
                migrations.RenameField(model_name="documentseries", old_name="voucher_type", new_name="document_type"),
                migrations.RenameField(model_name="salesdocument", old_name="voucher_type", new_name="document_type"),
                migrations.RenameField(model_name="salesdocument", old_name="reference_voucher", new_name="reference_document"),
                migrations.RenameField(model_name="salesdocumentline", old_name="voucher", new_name="sales_document"),
                migrations.AlterModelTable(name="salesdocument", table="sales_documents"),
                migrations.AlterModelTable(name="salesdocumentline", table="sales_document_lines"),
            ],
        ),
        migrations.AlterUniqueTogether(
            name="documentseries",
            unique_together={("company", "store", "document_type", "series")},
        ),
        migrations.AlterField(
            model_name="salesdocument", name="store",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sales_documents", to="companies.store"),
        ),
        migrations.AlterField(
            model_name="salesdocument", name="customer",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sales_documents", to="partners.customer"),
        ),
        migrations.AlterField(
            model_name="salesdocument", name="series",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sales_documents", to="sales.documentseries"),
        ),
        migrations.AlterField(
            model_name="salesdocument", name="sale_order",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sales_documents", to="sales.saleorder"),
        ),
        migrations.AlterField(
            model_name="salesdocument", name="created_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sales_documents", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name="salesdocumentline", name="sale_order_line",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sales_document_lines", to="sales.saleorderline"),
        ),
        migrations.AddConstraint(
            model_name="salesdocument",
            constraint=models.UniqueConstraint(
                condition=models.Q(("number", ""), _negated=True),
                fields=("series", "number"),
                name="uniq_issued_sales_document_number",
            ),
        ),
    ]
