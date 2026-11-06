from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from apps.inventory.pricing import tax_rate_for_company
from apps.sales.models import SalesQuotation
from apps.sales.services import _calculate_line


class Command(BaseCommand):
    help = (
        "Audita cotizaciones gravadas guardadas con tasa IGV cero y, con "
        "--apply, recalcula sus lineas y totales."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Guarda las correcciones. Sin esta opcion solo se muestra la auditoria.",
        )
        parser.add_argument(
            "--company-id",
            help="Limita la auditoria a una empresa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        quotations = SalesQuotation.objects.filter(
            lines__tax_type="10",
            lines__igv_rate=0,
            lines__igv_amount=0,
            lines__total=F("lines__subtotal"),
        ).select_related("store__company").prefetch_related("lines").distinct()

        company_id = options.get("company_id")
        if company_id:
            quotations = quotations.filter(store__company_id=company_id)

        affected = 0
        skipped = 0
        for quotation in quotations:
            if not quotation.store_id:
                skipped += 1
                continue
            default_rate = tax_rate_for_company(
                quotation.store.company_id,
                on_date=quotation.issue_date,
            )
            if default_rate <= 0:
                skipped += 1
                continue

            recalculated = []
            for line in quotation.lines.all():
                rate = line.igv_rate
                if (
                    line.tax_type == "10"
                    and line.igv_rate == 0
                    and line.igv_amount == 0
                    and line.total == line.subtotal
                ):
                    rate = default_rate
                totals = _calculate_line({
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                    "discount_amount": line.discount_amount,
                    "tax_type": line.tax_type,
                    "igv_rate": rate,
                })
                recalculated.append((line, rate, totals))

            subtotal = sum((item[2]["subtotal"] for item in recalculated), Decimal("0"))
            igv_total = sum((item[2]["igv_amount"] for item in recalculated), Decimal("0"))
            total = sum((item[2]["total"] for item in recalculated), Decimal("0"))
            reference = f"{quotation.series_code}-{quotation.number or 'BORRADOR'}"
            self.stdout.write(
                f"{reference}: {quotation.total} -> {total} "
                f"(IGV {quotation.igv_total} -> {igv_total})"
            )
            affected += 1

            if not apply_changes:
                continue

            with transaction.atomic():
                for line, rate, totals in recalculated:
                    line.igv_rate = rate
                    line.subtotal = totals["subtotal"]
                    line.igv_amount = totals["igv_amount"]
                    line.total = totals["total"]
                    line.save(update_fields=["igv_rate", "subtotal", "igv_amount", "total"])
                quotation.subtotal = subtotal
                quotation.igv_total = igv_total
                quotation.total = total
                quotation.save(update_fields=["subtotal", "igv_total", "total"])

        mode = "reparadas" if apply_changes else "detectadas"
        self.stdout.write(self.style.SUCCESS(
            f"Cotizaciones {mode}: {affected}. Omitidas: {skipped}."
        ))
        if affected and not apply_changes:
            self.stdout.write("Ejecute nuevamente con --apply para guardar las correcciones.")

