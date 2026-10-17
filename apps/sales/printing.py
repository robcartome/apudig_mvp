"""Componentes compartidos para impresiones comerciales A4 y ticket."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import base64
from io import BytesIO

import qrcode

from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.text import slugify

from apps.companies.models import CompanyBranding, CompanyDocumentSettings
from apps.core.amount_words import amount_to_spanish_words

from .quotation_pdf import build_quotation_pdf, normalize_pdf_format


@dataclass
class CommercialPrintDocument:
    source: object
    kind: str
    pos_transaction: object = None

    @property
    def pk(self):
        return self.source.pk

    @property
    def store(self):
        return self.source.store

    @property
    def company(self):
        return self.store.company

    @property
    def lines(self):
        return self.source.lines

    @property
    def series_code(self):
        return self.source.series_code

    @property
    def number(self):
        return self.source.number

    @property
    def reference(self):
        number = self.source.number
        if self.kind == "quotation":
            number = f"{int(number):08d}"
        return f"{self.source.series_code}-{number or 'BORRADOR'}"

    @property
    def document_label(self):
        if self.kind == "quotation":
            return "Cotización"
        if self.kind == "order":
            return "Orden de venta"
        label = self.source.document_type.name
        if self.source.document_type.is_sunat and "electr" not in label.lower():
            label = f"{label} electrónica"
        return label

    @property
    def settings_code(self):
        if self.kind == "quotation":
            return "COT"
        if self.kind == "order":
            return "OV"
        return self.source.document_type.code

    @property
    def issue_date(self):
        value = self.source.issue_date
        return value.date() if isinstance(value, datetime) else value

    @property
    def valid_until(self):
        if self.kind == "quotation":
            return self.source.valid_until
        return getattr(self.source, "due_date", None)

    @property
    def validity_label(self):
        return "Válido hasta" if self.kind == "quotation" else "Vencimiento"

    @property
    def payment_method(self):
        value = getattr(self.source, "payment_method", None)
        if value:
            return str(value)
        days = getattr(self.source, "payment_term_days", 0)
        return f"Crédito {days} días" if days else "Contado"

    @property
    def seller_name(self):
        value = getattr(self.source, "seller_name", "")
        if value:
            return value
        seller = getattr(self.source, "seller", None)
        if seller:
            return str(seller)
        if self.pos_transaction and self.pos_transaction.cashier:
            return self.pos_transaction.cashier.display_name
        creator = getattr(self.source, "created_by", None)
        return creator.display_name if creator else ""

    @property
    def total_discount(self):
        return getattr(self.source, "total_discount", Decimal("0")) or Decimal("0")

    @property
    def amount_in_words(self):
        return amount_to_spanish_words(self.source.total, self.source.currency)

    @property
    def tax_totals(self):
        if self.kind == "sales":
            return {
                "10": self.source.taxable_amount,
                "20": self.source.exempt_amount,
                "30": self.source.unaffected_amount,
                "40": self.source.export_amount,
                "11": self.source.free_amount,
            }
        totals = {code: Decimal("0") for code in ("10", "20", "30", "40", "11")}
        for line in self.lines.all():
            totals[line.tax_type] = totals.get(line.tax_type, Decimal("0")) + line.subtotal
        return totals

    @property
    def taxable_amount(self):
        return self.tax_totals["10"]

    @property
    def exempt_amount(self):
        return self.tax_totals["20"]

    @property
    def unaffected_amount(self):
        return self.tax_totals["30"]

    @property
    def export_amount(self):
        return self.tax_totals["40"]

    @property
    def free_amount(self):
        return self.tax_totals["11"]

    @property
    def qr_payload(self):
        if self.kind != "sales" or not self.source.sunat_hash:
            return ""
        if self.source.document_type.code not in {"01", "03", "07", "08"}:
            return ""
        return "|".join((
            self.company.ruc,
            self.source.document_type.code,
            self.source.series_code,
            self.source.number,
            str(self.source.igv_total),
            str(self.source.total),
            self.issue_date.isoformat(),
            self.source.customer_document_type,
            self.source.customer_document_number,
            self.source.sunat_hash,
        ))

    def get_status_display(self):
        return self.source.get_status_display()

    def __getattr__(self, name):
        return getattr(self.source, name)


def print_configuration(print_document):
    company = print_document.company
    document_settings = CompanyDocumentSettings.objects.filter(
        company=company,
        document_type=print_document.settings_code,
    ).first()
    branding = CompanyBranding.objects.filter(company=company).first()
    return document_settings, branding


def printable_logo_url(branding):
    if not branding:
        return ""
    if branding.logo_file:
        return reverse("company_branding_logo", args=[branding.company_id])
    return branding.pdf_logo_url or branding.app_logo_url or ""


def qr_data_uri(payload):
    if not payload:
        return ""
    stream = BytesIO()
    qrcode.make(payload).save(stream, format="PNG")
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")


def render_commercial_print(
    request, print_document, *, back_url, pdf_url, default_format_override=None
):
    document_settings, branding = print_configuration(print_document)
    pdf_format = normalize_pdf_format(
        request.GET.get("format"),
        default_format_override or getattr(document_settings, "format", "A4"),
    )
    return render(request, "sales/pdf/quotation_print.html", {
        "quotation": print_document,
        "company": print_document.company,
        "document_settings": document_settings,
        "branding": branding,
        "pdf_format": pdf_format,
        "company_logo_url": printable_logo_url(branding),
        "back_url": back_url,
        "pdf_url": f"{pdf_url}?format={pdf_format}",
        "qr_data_uri": qr_data_uri(print_document.qr_payload),
    })


def commercial_pdf_response(request, print_document):
    document_settings, branding = print_configuration(print_document)
    pdf_format = normalize_pdf_format(
        request.GET.get("format"), getattr(document_settings, "format", "A4")
    )
    payload = build_quotation_pdf(
        print_document,
        pdf_format=pdf_format,
        document_settings=document_settings,
        branding=branding,
    )
    filename = f"{slugify(print_document.document_label)}-{print_document.reference}-{pdf_format.lower()}.pdf"
    response = HttpResponse(payload, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
