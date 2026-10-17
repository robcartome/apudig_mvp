"""Generación de cotizaciones descargables en formatos A4 y ticket de 80 mm."""

import base64
import ipaddress
import socket
from decimal import Decimal
from html import escape
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.contrib.staticfiles import finders
import qrcode
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.companies.logo_images import normalized_logo_stream
from apps.core.amount_words import amount_to_spanish_words


PDF_FORMATS = {"A4", "TICKET"}


def normalize_pdf_format(value, default="A4"):
    requested = (value or default or "A4").upper()
    return requested if requested in PDF_FORMATS else "A4"


def _money(value):
    return f"{Decimal(value or 0):,.2f}"


def _number(value):
    number = Decimal(value or 0)
    return format(number.normalize(), "f") if number else "0"


def _currency_symbol(code):
    return {"PEN": "S/", "USD": "$", "EUR": "€"}.get(code, code)


def _safe_color(value, fallback="#1769aa"):
    try:
        return colors.HexColor(value or fallback)
    except (ValueError, TypeError):
        return colors.HexColor(fallback)


def _safe_remote_logo(url):
    """Descarga únicamente logos HTTPS públicos, evitando destinos internos."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    try:
        addresses = {
            item[4][0] for item in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        }
        if not addresses:
            return None
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global:
                return None
        request = Request(url, headers={"User-Agent": "APUDIG-PDF/1.0"})

        class NoRedirects(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        with build_opener(NoRedirects).open(request, timeout=4) as response:
            if response.headers.get_content_type() not in {"image/png", "image/jpeg", "image/webp"}:
                return None
            payload = response.read(5 * 1024 * 1024 + 1)
            return BytesIO(payload) if len(payload) <= 5 * 1024 * 1024 else None
    except (OSError, ValueError):
        return None


def _logo_source(url):
    if not url:
        return None
    local_path = Path(str(url))
    if local_path.is_file():
        return str(local_path)
    if url.startswith("data:image/") and ";base64," in url:
        try:
            return BytesIO(base64.b64decode(url.split(",", 1)[1], validate=True))
        except (ValueError, TypeError):
            return None
    if url.startswith(settings.MEDIA_URL):
        path = Path(settings.MEDIA_ROOT) / url.removeprefix(settings.MEDIA_URL)
        return str(path) if path.is_file() else None
    if url.startswith(settings.STATIC_URL):
        return finders.find(url.removeprefix(settings.STATIC_URL))
    return _safe_remote_logo(url)


def _logo(url, *, ticket=False):
    source = _logo_source(url)
    if not source:
        return None
    try:
        image = Image(normalized_logo_stream(source))
        max_width = 62 * mm if ticket else 90 * mm
        max_height = 28 * mm if ticket else 30 * mm
        ratio = min(max_width / image.imageWidth, max_height / image.imageHeight)
        image.drawWidth = image.imageWidth * ratio
        image.drawHeight = image.imageHeight * ratio
        image.hAlign = "CENTER" if ticket else "LEFT"
        return image
    except (OSError, ValueError):
        return None


def _styles(primary):
    sample = getSampleStyleSheet()
    return {
        "body": ParagraphStyle(
            "QuoteBody", parent=sample["Normal"], fontName="Helvetica",
            fontSize=8.2, leading=10.2, textColor=colors.HexColor("#25313c"),
        ),
        "small": ParagraphStyle(
            "QuoteSmall", parent=sample["Normal"], fontName="Helvetica",
            fontSize=7, leading=8.5, textColor=colors.HexColor("#52616b"),
        ),
        "company": ParagraphStyle(
            "QuoteCompany", parent=sample["Heading1"], fontName="Helvetica-Bold",
            fontSize=14, leading=16, textColor=primary, spaceAfter=2,
        ),
        "title": ParagraphStyle(
            "QuoteTitle", parent=sample["Heading1"], fontName="Helvetica-Bold",
            fontSize=14, leading=16, alignment=TA_CENTER, textColor=colors.HexColor("#17212b"),
        ),
        "section": ParagraphStyle(
            "QuoteSection", parent=sample["Heading2"], fontName="Helvetica-Bold",
            fontSize=8, leading=10, textColor=primary, spaceBefore=5, spaceAfter=3,
        ),
        "right": ParagraphStyle(
            "QuoteRight", parent=sample["Normal"], fontName="Helvetica",
            fontSize=8, leading=10, alignment=TA_RIGHT,
        ),
        "ticket": ParagraphStyle(
            "TicketBody", parent=sample["Normal"], fontName="Helvetica",
            fontSize=7.5, leading=9.2, textColor=colors.black,
        ),
        "ticket_center": ParagraphStyle(
            "TicketCenter", parent=sample["Normal"], fontName="Helvetica",
            fontSize=7.5, leading=9.2, alignment=TA_CENTER,
        ),
        "ticket_title": ParagraphStyle(
            "TicketTitle", parent=sample["Heading1"], fontName="Helvetica-Bold",
            fontSize=11, leading=13, alignment=TA_CENTER,
        ),
    }


def _p(value, style, *, bold=False):
    text = escape(str(value or "—"))
    return Paragraph(f"<b>{text}</b>" if bold else text, style)


def _line_name(line):
    return line.description if getattr(line, "is_manual", False) else line.product.name


def _line_code(line):
    return line.product_code or ("" if getattr(line, "is_manual", False) else line.product.sku)


def _tax_totals(quotation):
    configured = getattr(quotation, "tax_totals", None)
    if configured is not None:
        return configured
    totals = {code: Decimal("0") for code in ("10", "20", "30", "40", "11")}
    for line in quotation.lines.all():
        totals[line.tax_type] = totals.get(line.tax_type, Decimal("0")) + line.subtotal
    return totals


def _reference(document):
    if hasattr(document, "reference"):
        return document.reference
    return f"{document.series_code}-{document.number:08d}"


def _document_label(document):
    return getattr(document, "document_label", "Cotización")


def _qr_image(payload, size=27 * mm):
    if not payload:
        return None
    image = qrcode.make(payload)
    stream = BytesIO()
    image.save(stream, format="PNG")
    stream.seek(0)
    result = Image(stream, width=size, height=size)
    result.hAlign = "LEFT"
    return result


def _a4_story(quotation, company, logo_url, footer_text, primary, styles):
    story = []
    company_parts = []
    logo = _logo(logo_url)
    if logo:
        company_parts.extend([logo, Spacer(1, 2 * mm)])
    company_parts.extend([
        _p(company.name, styles["company"]),
        _p(f"RUC: {company.ruc}", styles["body"], bold=True),
    ])
    if company.address:
        company_parts.append(_p(company.address, styles["small"]))
    contact = " · ".join(filter(None, [company.phone, company.email]))
    if contact:
        company_parts.append(_p(contact, styles["small"]))
    if quotation.store:
        company_parts.append(_p(f"Sucursal: {quotation.store.name}", styles["small"]))

    reference = _reference(quotation)
    document_box = Table(
        [[_p(f"RUC: {company.ruc}", styles["title"])],
         [_p(_document_label(quotation).upper(), styles["title"])],
         [_p(reference, styles["title"])],
         [_p(quotation.get_status_display().upper(), styles["small"], bold=True)]],
        colWidths=[58 * mm],
    )
    document_box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor("#25313c")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    header = Table([[company_parts, document_box]], colWidths=[119 * mm, 63 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.extend([header, Spacer(1, 5 * mm)])

    client_rows = [
        [_p("RAZÓN SOCIAL", styles["small"], bold=True), _p(quotation.customer_legal_name, styles["body"]),
         _p("DOCUMENTO", styles["small"], bold=True), _p(quotation.customer_document_number, styles["body"])],
        [_p("DIRECCIÓN", styles["small"], bold=True), _p(quotation.customer_address, styles["body"]),
         _p("VENDEDOR", styles["small"], bold=True), _p(quotation.seller_name, styles["body"])],
    ]
    client = Table(client_rows, colWidths=[25 * mm, 80 * mm, 22 * mm, 55 * mm])
    client.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), .7, colors.HexColor("#6d7882")),
        ("INNERGRID", (0, 0), (-1, -1), .25, colors.HexColor("#c5ccd2")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f2f5f7")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f2f5f7")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([client, Spacer(1, 2 * mm)])

    metadata = Table([
        [_p("FECHA DE EMISIÓN", styles["small"], bold=True),
         _p("VÁLIDO HASTA", styles["small"], bold=True),
         _p("CONDICIÓN DE PAGO", styles["small"], bold=True),
         _p("MONEDA", styles["small"], bold=True)],
        [_p(quotation.issue_date.strftime("%d/%m/%Y"), styles["body"]),
         _p(quotation.valid_until.strftime("%d/%m/%Y") if quotation.valid_until else "—", styles["body"]),
         _p(str(quotation.payment_method or "—"), styles["body"]),
         _p(quotation.currency, styles["body"])],
    ], colWidths=[45.5 * mm] * 4)
    metadata.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), .7, colors.HexColor("#6d7882")),
        ("INNERGRID", (0, 0), (-1, -1), .35, colors.HexColor("#aeb8c0")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf2f8")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([metadata, Spacer(1, 3 * mm)])

    line_data = [[
        _p("Código", styles["small"], bold=True), _p("Cantidad", styles["small"], bold=True),
        _p("Unidad", styles["small"], bold=True), _p("Descripción", styles["small"], bold=True),
        _p("Valor unit.", styles["small"], bold=True), _p("P. unit.", styles["small"], bold=True),
        _p("Total", styles["small"], bold=True),
    ]]
    for line in quotation.lines.all():
        line_data.append([
            _p(_line_code(line), styles["small"]), _p(_number(line.quantity), styles["right"]),
            _p(line.unit_code, styles["small"]), _p(_line_name(line), styles["body"]),
            _p(_money(line.unit_price), styles["right"]), _p(_money(line.price_unit), styles["right"]),
            _p(_money(line.total), styles["right"]),
        ])
    line_data.append([
        _p(amount_to_spanish_words(quotation.total, quotation.currency), styles["small"], bold=True),
        "", "", "", "", "", "",
    ])
    lines = Table(
        line_data, repeatRows=1,
        colWidths=[21 * mm, 16 * mm, 16 * mm, 73 * mm, 20 * mm, 18 * mm, 18 * mm],
    )
    lines.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), .7, colors.HexColor("#59656f")),
        ("INNERGRID", (0, 0), (-1, -1), .25, colors.HexColor("#bdc5cb")),
        ("BACKGROUND", (0, 0), (-1, 0), primary),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("SPAN", (0, -1), (-1, -1)),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f4f7f9")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([lines, Spacer(1, 3 * mm)])

    tax = _tax_totals(quotation)
    symbol = _currency_symbol(quotation.currency)
    totals_data = [
        [_p("Op. gravadas", styles["small"]), _p(f"{symbol} {_money(tax['10'])}", styles["right"])],
        [_p("Op. exoneradas", styles["small"]), _p(f"{symbol} {_money(tax['20'])}", styles["right"])],
        [_p("Op. inafectas", styles["small"]), _p(f"{symbol} {_money(tax['30'])}", styles["right"])],
        [_p("Descuentos", styles["small"]), _p(f"{symbol} {_money(quotation.total_discount)}", styles["right"])],
        [_p("IGV", styles["small"]), _p(f"{symbol} {_money(quotation.igv_total)}", styles["right"])],
        [_p("TOTAL", styles["body"], bold=True), _p(f"{symbol} {_money(quotation.total)}", styles["right"], bold=True)],
    ]
    totals = Table(totals_data, colWidths=[38 * mm, 28 * mm])
    totals.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), .7, colors.HexColor("#59656f")),
        ("LINEABOVE", (0, -1), (-1, -1), 1, primary),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eaf2f8")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    notes = []
    qr = _qr_image(getattr(quotation, "qr_payload", ""))
    if qr:
        notes.extend([qr, Spacer(1, 1.5 * mm)])
    if quotation.notes:
        notes.extend([_p("INFORMACIÓN ADICIONAL", styles["section"]), _p(quotation.notes, styles["body"])])
    if quotation.internal_reference:
        notes.append(_p(f"Referencia: {quotation.internal_reference}", styles["small"]))
    notes.append(_p(f"Importe total: {symbol} {_money(quotation.total)}", styles["body"], bold=True))
    closing = Table([[notes, totals]], colWidths=[112 * mm, 70 * mm])
    closing.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.extend([KeepTogether(closing), Spacer(1, 8 * mm)])
    if footer_text:
        story.append(_p(footer_text, styles["small"]))
    return story


def _ticket_story(quotation, company, logo_url, footer_text, styles):
    story = []
    logo = _logo(logo_url, ticket=True)
    if logo:
        story.extend([logo, Spacer(1, 1.5 * mm)])
    story.extend([
        _p(company.name, styles["ticket_title"]),
        _p(f"RUC: {company.ruc}", styles["ticket_center"], bold=True),
    ])
    for text in (company.address, company.phone, company.email):
        if text:
            story.append(_p(text, styles["ticket_center"]))
    story.extend([
        Spacer(1, 2 * mm),
        _p(_document_label(quotation).upper(), styles["ticket_title"]),
        _p(_reference(quotation), styles["ticket_center"], bold=True),
        _p(f"Fecha: {quotation.issue_date:%d/%m/%Y}", styles["ticket_center"]),
        Spacer(1, 2 * mm),
    ])
    customer = [
        [_p("Cliente:", styles["ticket"], bold=True), _p(quotation.customer_legal_name, styles["ticket"])],
        [_p("Doc.:", styles["ticket"], bold=True), _p(quotation.customer_document_number, styles["ticket"])],
    ]
    if quotation.customer_address:
        customer.append([_p("Dirección:", styles["ticket"], bold=True), _p(quotation.customer_address, styles["ticket"])])
    customer_table = Table(customer, colWidths=[15 * mm, 53 * mm])
    customer_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.extend([customer_table, Spacer(1, 2 * mm)])

    rows = [[_p("Descripción", styles["ticket"], bold=True),
             _p("Cant. x P.U.", styles["ticket"], bold=True),
             _p("Total", styles["ticket"], bold=True)]]
    for line in quotation.lines.all():
        code = _line_code(line)
        label = f"{code} - {_line_name(line)}" if code else _line_name(line)
        rows.append([
            _p(label, styles["ticket"]),
            _p(f"{_number(line.quantity)} x {_money(line.price_unit)}", styles["ticket"]),
            _p(_money(line.total), styles["ticket"]),
        ])
    rows.append([
        _p(amount_to_spanish_words(quotation.total, quotation.currency), styles["ticket"], bold=True),
        "", "",
    ])
    line_table = Table(rows, repeatRows=1, colWidths=[35 * mm, 20 * mm, 13 * mm])
    line_table.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), .7, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), .7, colors.black),
        ("LINEBELOW", (0, -1), (-1, -1), .7, colors.black),
        ("SPAN", (0, -1), (-1, -1)),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([line_table, Spacer(1, 2 * mm)])
    symbol = _currency_symbol(quotation.currency)
    totals = Table([
        [_p("Subtotal", styles["ticket"]), _p(f"{symbol} {_money(quotation.subtotal)}", styles["ticket"], bold=True)],
        [_p("Descuentos", styles["ticket"]), _p(f"- {symbol} {_money(quotation.total_discount)}", styles["ticket"], bold=True)],
        [_p("IGV", styles["ticket"]), _p(f"{symbol} {_money(quotation.igv_total)}", styles["ticket"], bold=True)],
        [_p("TOTAL", styles["ticket_title"]), _p(f"{symbol} {_money(quotation.total)}", styles["ticket_title"])],
    ], colWidths=[38 * mm, 30 * mm])
    totals.setStyle(TableStyle([
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.extend([totals, Spacer(1, 2 * mm)])
    if quotation.valid_until:
        story.append(_p(f"Válido hasta: {quotation.valid_until:%d/%m/%Y}", styles["ticket_center"]))
    if quotation.seller_name:
        story.append(_p(f"Vendedor: {quotation.seller_name}", styles["ticket_center"]))
    if quotation.notes:
        story.extend([Spacer(1, 1 * mm), _p(f"Notas: {quotation.notes}", styles["ticket"])])
    qr = _qr_image(getattr(quotation, "qr_payload", ""), size=25 * mm)
    if qr:
        story.extend([Spacer(1, 2 * mm), qr])
    story.extend([
        Spacer(1, 3 * mm),
        _p(footer_text or "Gracias por su preferencia.", styles["ticket_center"]),
        _p("Documento generado por APUDIG", styles["ticket_center"]),
    ])
    return story


def build_quotation_pdf(quotation, *, pdf_format="A4", document_settings=None, branding=None):
    pdf_format = normalize_pdf_format(pdf_format)
    company = quotation.store.company
    primary = _safe_color(getattr(branding, "primary_color", None))
    styles = _styles(primary)
    logo_url = (
        getattr(document_settings, "logo_url_override", "")
        or (branding.printable_logo_source() if branding else "")
    )
    footer_text = getattr(document_settings, "footer_text", "")
    buffer = BytesIO()
    if pdf_format == "TICKET":
        line_count = quotation.lines.count()
        description_length = sum(len(_line_name(line)) for line in quotation.lines.all())
        notes_length = len(quotation.notes or "")
        qr_height = 32 if getattr(quotation, "qr_payload", "") else 0
        height = max(
            145 * mm,
            (112 + line_count * 10 + description_length / 16 + notes_length / 8 + qr_height) * mm,
        )
        document = SimpleDocTemplate(
            buffer, pagesize=(80 * mm, height),
            leftMargin=6 * mm, rightMargin=6 * mm, topMargin=5 * mm, bottomMargin=6 * mm,
            title=f"{_document_label(quotation)} {_reference(quotation)}",
            author=company.name,
        )
        story = _ticket_story(quotation, company, logo_url, footer_text, styles)
    else:
        document = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=14 * mm,
            title=f"{_document_label(quotation)} {_reference(quotation)}",
            author=company.name,
        )
        story = _a4_story(quotation, company, logo_url, footer_text, primary, styles)

    def footer(canvas, doc):
        if pdf_format != "A4":
            return
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d8dde2"))
        canvas.line(14 * mm, 10 * mm, A4[0] - 14 * mm, 10 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#66727c"))
        canvas.drawString(14 * mm, 6.5 * mm, "Documento generado por APUDIG")
        canvas.drawRightString(A4[0] - 14 * mm, 6.5 * mm, f"Página {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
