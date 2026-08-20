from django.db import migrations, models
import django.db.models.deletion


def migrate_document_types(apps, schema_editor):
    DocumentType = apps.get_model("partners", "DocumentType")
    BusinessDocumentType = apps.get_model("sales", "BusinessDocumentType")
    DocumentSeries = apps.get_model("sales", "DocumentSeries")
    SalesDocument = apps.get_model("sales", "SalesDocument")
    SaleOrder = apps.get_model("sales", "SaleOrder")

    id_map = {}
    for old in BusinessDocumentType.objects.all():
        target, _ = DocumentType.objects.update_or_create(
            code=old.code,
            defaults={
                "name": old.name,
                "abbreviation": old.code,
                "category": old.category,
                "is_sunat": old.is_sunat,
                "sunat_code": old.sunat_code,
                "affects_stock": old.affects_stock,
                "affects_accounting": old.affects_accounting,
                "active": old.active,
            },
        )
        id_map[old.pk] = target.pk

    defaults = {
        "NV": ("Nota de Venta", "SALES", False),
        "01": ("Factura", "SALES", True),
        "03": ("Boleta de Venta", "SALES", True),
        "07": ("Nota de Crédito", "BILLING", True),
        "08": ("Nota de Débito", "BILLING", True),
        "09": ("Guía de Remisión Remitente", "LOGISTICS", True),
        "OV": ("Orden de Venta Interna", "INTERNAL", False),
        "COT": ("Cotización", "INTERNAL", False),
    }
    codes = set(DocumentSeries.objects.values_list("document_type", flat=True))
    codes.update(SalesDocument.objects.values_list("document_type", flat=True))
    for code in codes:
        if not code:
            continue
        name, category, is_sunat = defaults.get(code, (code, "INTERNAL", False))
        DocumentType.objects.update_or_create(
            code=code,
            defaults={"name": name, "abbreviation": code, "category": category,
                      "is_sunat": is_sunat, "sunat_code": code if is_sunat else "", "active": True},
        )

    by_code = {obj.code: obj.pk for obj in DocumentType.objects.all()}
    for series in DocumentSeries.objects.all():
        series.document_type_ref_id = by_code[series.document_type]
        series.save(update_fields=["document_type_ref"])
    for document in SalesDocument.objects.all():
        document.document_type_ref_id = by_code[document.document_type]
        document.save(update_fields=["document_type_ref"])
    for order in SaleOrder.objects.all():
        order.document_type_ref_id = id_map[order.document_type_id]
        order.save(update_fields=["document_type_ref"])


class Migration(migrations.Migration):
    dependencies = [("partners", "0004_documenttype_commercial_fields"), ("sales", "0006_salesdocument_export_amount_and_more")]

    operations = [
        migrations.AddField(model_name="documentseries", name="document_type_ref", field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="document_series_new", to="partners.documenttype")),
        migrations.AddField(model_name="salesdocument", name="document_type_ref", field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="sales_documents_new", to="partners.documenttype")),
        migrations.AddField(model_name="saleorder", name="document_type_ref", field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="sale_orders_new", to="partners.documenttype")),
        migrations.RunPython(migrate_document_types, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(name="documentseries", unique_together=set()),
        migrations.RemoveField(model_name="documentseries", name="document_type"),
        migrations.RemoveField(model_name="salesdocument", name="document_type"),
        migrations.RemoveField(model_name="saleorder", name="document_type"),
        migrations.RenameField(model_name="documentseries", old_name="document_type_ref", new_name="document_type"),
        migrations.RenameField(model_name="salesdocument", old_name="document_type_ref", new_name="document_type"),
        migrations.RenameField(model_name="saleorder", old_name="document_type_ref", new_name="document_type"),
        migrations.AlterField(model_name="documentseries", name="document_type", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="document_series", to="partners.documenttype")),
        migrations.AlterField(model_name="salesdocument", name="document_type", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sales_documents", to="partners.documenttype")),
        migrations.AlterField(model_name="saleorder", name="document_type", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sale_orders", to="partners.documenttype")),
        migrations.AlterUniqueTogether(name="documentseries", unique_together={("company", "store", "document_type", "series")}),
        migrations.DeleteModel(name="BusinessDocumentType"),
    ]
