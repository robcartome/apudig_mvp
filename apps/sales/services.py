"""
sales/services.py — Lógica de negocio del ciclo comercial.

Flujo principal: SalesQuotation → SaleOrder → SalesDocument

Reglas:
- Toda creación de documento usa transaction.atomic().
- La numeración de series se hace con select_for_update() para evitar duplicados.
- Los snapshots del cliente (document_number, legal_name, etc.) se copian al
  momento de la creación; nunca se leen del cliente en tiempo de consulta.
"""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    BusinessDocumentType,
    DocumentSeries,
    QUOTATION_STATUS_CHOICES,
    SalesQuotation,
    SalesQuotationLine,
    SaleOrder,
    SaleOrderLine,
    TAX_TYPE_CHOICES,
    SalesDocument,
    SalesDocumentLine,
)


def _next_series_number(series: DocumentSeries) -> int:
    """
    Obtiene y reserva el siguiente número de la serie con bloqueo pesimista.
    Siempre llamar dentro de transaction.atomic().
    """
    if series is None:
        raise ValueError("Debe seleccionar una serie documental activa.")
    locked = DocumentSeries.objects.select_for_update().get(pk=series.pk)
    locked.current_number += 1
    locked.save(update_fields=["current_number"])
    return locked.current_number

@transaction.atomic
def create_document_series(
    company_id: str,
    store_id: str | None,
    document_type: str,
    series_code: str,
) -> DocumentSeries:
    """
    Crea una nueva serie. Lanza ValueError si ya existe la combinación.
    """
    series_code = series_code.upper().strip()
    if DocumentSeries.objects.filter(
        company_id=company_id,
        store_id=store_id,
        document_type=document_type,
        series=series_code,
    ).exists():
        raise ValueError(f"Ya existe la serie '{series_code}' para este tipo y sucursal.")
    return DocumentSeries.objects.create(
        company_id=company_id,
        store_id=store_id,
        document_type=document_type,
        series=series_code,
    )


def toggle_series(series: DocumentSeries) -> DocumentSeries:
    """Activa o desactiva una serie."""
    series.active = not series.active
    series.save(update_fields=["active"])
    return series


def get_or_create_series(company_id: str, store_id: str | None, document_type: str, series_code: str) -> DocumentSeries:
    obj, _ = DocumentSeries.objects.get_or_create(
        company_id=company_id,
        store_id=store_id,
        document_type=document_type,
        series=series_code,
    )
    return obj


def _calculate_line(line: dict) -> dict:
    """
    Calcula subtotal, igv_amount y total de una línea de documento.
    Retorna dict con esas tres claves (Decimal).
    """
    quantity = Decimal(str(line["quantity"]))
    unit_price = Decimal(str(line["unit_price"]))
    discount = Decimal(str(line.get("discount_amount", 0)))
    igv_rate = Decimal(str(line.get("igv_rate", 18)))
    tax_type = line.get("tax_type", "10")

    subtotal = unit_price * quantity - discount
    igv_amount = subtotal * igv_rate / Decimal("100") if tax_type == "10" else Decimal("0")
    return {
        "subtotal": subtotal.quantize(Decimal("0.01")),
        "igv_amount": igv_amount.quantize(Decimal("0.01")),
        "total": (subtotal + igv_amount).quantize(Decimal("0.01")),
    }



@transaction.atomic
def create_quotation(store_id: str, customer, series: DocumentSeries, lines: list[dict], created_by=None, **kwargs) -> SalesQuotation:
    """
    Crea una cotización, asigna número de serie y calcula totales.
    lines: lista de dict con claves: product, description, quantity,
           unit_price, discount_amount (opcional), tax_type (opcional),
           igv_rate (opcional), memo (opcional).
    """
    number = _next_series_number(series)

    calculated_lines = [_calculate_line(l) for l in lines]
    subtotal = sum(l["subtotal"] for l in calculated_lines)
    igv_total = sum(l["igv_amount"] for l in calculated_lines)
    total_discount = sum(l.get("discount_amount", Decimal("0")) for l in lines)
    total = subtotal + igv_total

    quotation = SalesQuotation.objects.create(
        store_id=store_id,
        customer=customer,
        customer_document_type=customer.document_type,
        customer_document_number=customer.document_number,
        customer_legal_name=customer.legal_name,
        customer_address=getattr(customer, "address", ""),
        customer_ubigeo=getattr(customer, "ubigeo", ""),
        series=series,
        series_code=series.series,
        number=number,
        subtotal=subtotal,
        igv_total=igv_total,
        total_discount=total_discount,
        total=total,
        created_by=created_by,
        **kwargs,
    )
    for raw, calc in zip(lines, calculated_lines):
        SalesQuotationLine.objects.create(
            quotation=quotation,
            product=raw["product"],
            description=raw.get("description", ""),
            quantity=raw["quantity"],
            unit_price=raw["unit_price"],
            unit_code=raw.get("unit_code", "NIU"),
            discount_amount=raw.get("discount_amount", Decimal("0")),
            tax_type=raw.get("tax_type", "10"),
            igv_rate=raw.get("igv_rate", Decimal("18")),
            sunat_product_code=raw.get("sunat_product_code", ""),
            product_code=raw.get("product_code", ""),
            memo=raw.get("memo", ""),
            subtotal=calc["subtotal"],
            igv_amount=calc["igv_amount"],
            total=calc["total"],
        )
    return quotation


@transaction.atomic
def update_quotation(quotation_id, lines: list[dict], created_by=None, **kwargs) -> SalesQuotation:
    """
    Actualiza cabecera y líneas de una cotización. Solo permite editar en estado DRAFT.
    Raises ValueError si la cotización no está en DRAFT.
    """
    quotation = (
        SalesQuotation.objects.select_for_update()
        .get(pk=quotation_id)
    )
    if quotation.status != "DRAFT":
        raise ValueError("Solo se pueden editar cotizaciones en estado Borrador.")

    for attr, value in kwargs.items():
        setattr(quotation, attr, value)

    calculated_lines = [_calculate_line(l) for l in lines]
    subtotal = sum(l["subtotal"] for l in calculated_lines)
    igv_total = sum(l["igv_amount"] for l in calculated_lines)
    total_discount = sum(l.get("discount_amount", Decimal("0")) for l in lines)
    total = subtotal + igv_total

    quotation.subtotal = subtotal
    quotation.igv_total = igv_total
    quotation.total_discount = total_discount
    quotation.total = total
    quotation.save(update_fields=list(kwargs.keys()) + ["subtotal", "igv_total", "total_discount", "total"])

    quotation.lines.all().delete()
    for raw, calc in zip(lines, calculated_lines):
        SalesQuotationLine.objects.create(
            quotation=quotation,
            product=raw["product"],
            description=raw.get("description", ""),
            quantity=raw["quantity"],
            unit_price=raw["unit_price"],
            unit_code=raw.get("unit_code", "NIU"),
            discount_amount=raw.get("discount_amount", Decimal("0")),
            tax_type=raw.get("tax_type", "10"),
            igv_rate=raw.get("igv_rate", Decimal("18")),
            sunat_product_code=raw.get("sunat_product_code", ""),
            product_code=raw.get("product_code", ""),
            memo=raw.get("memo", ""),
            subtotal=calc["subtotal"],
            igv_amount=calc["igv_amount"],
            total=calc["total"],
        )
    return quotation


def _approve_status_change(quotation, new_status: str, allowed_from: list[str]) -> SalesQuotation:
    if quotation.status not in allowed_from:
        allowed = ", ".join(allowed_from)
        raise ValueError(f"No se puede realizar esta acción desde el estado '{quotation.status}'. Estados permitidos: {allowed}.")
    quotation.status = new_status
    quotation.save(update_fields=["status"])
    return quotation


@transaction.atomic
def approve_quotation(quotation_id) -> SalesQuotation:
    q = SalesQuotation.objects.select_for_update().get(pk=quotation_id)
    return _approve_status_change(q, "APPROVED", ["DRAFT", "SENT"])


@transaction.atomic
def reject_quotation(quotation_id) -> SalesQuotation:
    q = SalesQuotation.objects.select_for_update().get(pk=quotation_id)
    return _approve_status_change(q, "REJECTED", ["DRAFT", "SENT"])


@transaction.atomic
def cancel_quotation(quotation_id) -> SalesQuotation:
    q = SalesQuotation.objects.select_for_update().get(pk=quotation_id)
    return _approve_status_change(q, "CANCELLED", ["DRAFT", "SENT", "APPROVED"])


# ── Órdenes de venta ──────────────────────────────────────────────────────────

@transaction.atomic
def create_sale_order(
    store_id: str,
    customer,
    document_type,
    series: DocumentSeries,
    lines: list[dict],
    created_by=None,
    **kwargs,
) -> SaleOrder:
    """
    Crea una orden de venta, asigna número de serie y calcula totales.
    lines: misma estructura que create_quotation.
    """
    number = _next_series_number(series)

    calculated_lines = [_calculate_line(l) for l in lines]
    subtotal = sum(l["subtotal"] for l in calculated_lines)
    igv_total = sum(l["igv_amount"] for l in calculated_lines)
    total_discount = sum(
        Decimal(str(l.get("discount_amount", 0))) for l in lines
    )
    total = subtotal + igv_total

    order = SaleOrder.objects.create(
        store_id=store_id,
        customer=customer,
        customer_document_type=customer.document_type,
        customer_document_number=customer.document_number,
        customer_legal_name=customer.legal_name,
        customer_address=getattr(customer, "address", ""),
        customer_ubigeo=getattr(customer, "ubigeo", ""),
        document_type=document_type,
        series=series,
        series_code=series.series,
        number=f"{number:08d}",
        subtotal=subtotal,
        igv_total=igv_total,
        total_discount=total_discount,
        total=total,
        created_by=created_by,
        **kwargs,
    )
    for raw, calc in zip(lines, calculated_lines):
        SaleOrderLine.objects.create(
            sale_order=order,
            product=raw["product"],
            description=raw.get("description", ""),
            quantity=raw["quantity"],
            unit_price=raw["unit_price"],
            unit_code=raw.get("unit_code", "NIU"),
            discount_amount=raw.get("discount_amount", Decimal("0")),
            tax_type=raw.get("tax_type", "10"),
            igv_rate=raw.get("igv_rate", Decimal("18")),
            sunat_product_code=raw.get("sunat_product_code", ""),
            product_code=raw.get("product_code", ""),
            subtotal=calc["subtotal"],
            igv_amount=calc["igv_amount"],
            total=calc["total"],
        )
    return order


@transaction.atomic
def create_order_from_quotation(
    quotation_id,
    document_type,
    series: DocumentSeries,
    created_by=None,
    **kwargs,
) -> SaleOrder:
    """
    Convierte una cotización APPROVED en orden de venta.
    Vincula la FK quotation y marca la cotización como INVOICED.
    """
    quotation = SalesQuotation.objects.select_for_update().get(pk=quotation_id)
    if quotation.status != "APPROVED":
        raise ValueError("Solo se pueden convertir cotizaciones en estado Aprobado.")

    lines = [
        {
            "product": line.product,
            "description": line.description,
            "quantity": line.quantity,
            "unit_price": line.unit_price,
            "unit_code": line.unit_code,
            "discount_amount": line.discount_amount,
            "tax_type": line.tax_type,
            "igv_rate": line.igv_rate,
            "sunat_product_code": line.sunat_product_code,
            "product_code": line.product_code,
        }
        for line in quotation.lines.all()
    ]

    order = create_sale_order(
        store_id=str(quotation.store_id) if quotation.store_id else None,
        customer=quotation.customer,
        document_type=document_type,
        series=series,
        lines=lines,
        created_by=created_by,
        issue_date=kwargs.pop("issue_date", timezone.now().date()),
        currency=quotation.currency,
        notes=quotation.notes,
        internal_reference=quotation.internal_reference,
        **kwargs,
    )
    # Vincula cotización y la marca INVOICED
    order.quotation = quotation
    order.save(update_fields=["quotation"])
    quotation.status = "CANCELLED"  # cotización queda cancelada/usada
    quotation.save(update_fields=["status"])
    return order


@transaction.atomic
def update_sale_order(order_id, lines: list[dict], **kwargs) -> SaleOrder:
    """Actualiza cabecera y líneas. Solo permite DRAFT."""
    order = SaleOrder.objects.select_for_update().get(pk=order_id)
    if order.status != "DRAFT":
        raise ValueError("Solo se pueden editar órdenes en estado Borrador.")

    for attr, value in kwargs.items():
        setattr(order, attr, value)

    calculated_lines = [_calculate_line(l) for l in lines]
    subtotal = sum(l["subtotal"] for l in calculated_lines)
    igv_total = sum(l["igv_amount"] for l in calculated_lines)
    total_discount = sum(
        Decimal(str(l.get("discount_amount", 0))) for l in lines
    )
    total = subtotal + igv_total

    order.subtotal = subtotal
    order.igv_total = igv_total
    order.total_discount = total_discount
    order.total = total
    order.save(
        update_fields=list(kwargs.keys()) + ["subtotal", "igv_total", "total_discount", "total"]
    )

    order.lines.all().delete()
    for raw, calc in zip(lines, calculated_lines):
        SaleOrderLine.objects.create(
            sale_order=order,
            product=raw["product"],
            description=raw.get("description", ""),
            quantity=raw["quantity"],
            unit_price=raw["unit_price"],
            unit_code=raw.get("unit_code", "NIU"),
            discount_amount=raw.get("discount_amount", Decimal("0")),
            tax_type=raw.get("tax_type", "10"),
            igv_rate=raw.get("igv_rate", Decimal("18")),
            sunat_product_code=raw.get("sunat_product_code", ""),
            product_code=raw.get("product_code", ""),
            subtotal=calc["subtotal"],
            igv_amount=calc["igv_amount"],
            total=calc["total"],
        )
    return order


@transaction.atomic
def confirm_order(order_id) -> SaleOrder:
    order = SaleOrder.objects.select_for_update().get(pk=order_id)
    if order.status != "DRAFT":
        raise ValueError("Solo se pueden confirmar órdenes en estado Borrador.")
    order.status = "CONFIRMED"
    order.save(update_fields=["status"])
    return order


@transaction.atomic
def cancel_order(order_id) -> SaleOrder:
    order = SaleOrder.objects.select_for_update().get(pk=order_id)
    if order.status not in ("DRAFT", "CONFIRMED"):
        raise ValueError(
            f"No se puede cancelar una orden en estado '{order.status}'."
        )
    order.status = "CANCELLED"
    order.save(update_fields=["status"])
    return order


# ── Comprobantes ──────────────────────────────────────────────────────────────

def _calc_sales_document_totals(lines: list[dict], calculated: list[dict]) -> dict:
    """Calcula totales desagregados para comprobante (gravado / exonerado / inafecto)."""
    taxable = Decimal("0")
    exempt = Decimal("0")
    unaffected = Decimal("0")
    igv_total = Decimal("0")
    total_discount = Decimal("0")

    for raw, calc in zip(lines, calculated):
        tax_type = raw.get("tax_type", "10")
        if tax_type == "10":
            taxable += calc["subtotal"]
        elif tax_type == "20":
            exempt += calc["subtotal"]
        else:
            unaffected += calc["subtotal"]
        igv_total += calc["igv_amount"]
        total_discount += Decimal(str(raw.get("discount_amount", 0)))

    subtotal = taxable + exempt + unaffected
    return {
        "subtotal": subtotal,
        "taxable_amount": taxable,
        "exempt_amount": exempt,
        "unaffected_amount": unaffected,
        "igv_total": igv_total,
        "total_discount": total_discount,
        "total": (subtotal + igv_total).quantize(Decimal("0.01")),
    }


@transaction.atomic
def create_sales_document_draft(
    store_id: str,
    customer,
    document_type: str,
    series: DocumentSeries,
    lines: list[dict],
    sale_order=None,
    created_by=None,
    **kwargs,
) -> SalesDocument:
    """
    Crea un comprobante en estado DRAFT sin asignar número (se reserva en issue_sales_document).
    lines: misma estructura que create_quotation.
    """
    calculated_lines = [_calculate_line(l) for l in lines]
    totals = _calc_sales_document_totals(lines, calculated_lines)

    sales_document = SalesDocument.objects.create(
        store_id=store_id,
        document_type=document_type,
        status="DRAFT",
        customer=customer,
        customer_document_type=customer.document_type,
        customer_document_number=customer.document_number,
        customer_legal_name=customer.legal_name,
        customer_address=getattr(customer, "address", ""),
        customer_ubigeo=getattr(customer, "ubigeo", ""),
        series=series,
        series_code=series.series,
        number="",        # se asignará en issue_sales_document
        sale_order=sale_order,
        created_by=created_by,
        **{k: v for k, v in {**totals, **kwargs}.items()},
    )
    for raw, calc in zip(lines, calculated_lines):
        SalesDocumentLine.objects.create(
            sales_document=sales_document,
            product=raw["product"],
            description=raw.get("description", ""),
            quantity=raw["quantity"],
            unit_price=raw["unit_price"],
            unit_code=raw.get("unit_code", "NIU"),
            discount_amount=raw.get("discount_amount", Decimal("0")),
            tax_type=raw.get("tax_type", "10"),
            igv_rate=raw.get("igv_rate", Decimal("18")),
            sunat_product_code=raw.get("sunat_product_code", ""),
            product_code=raw.get("product_code", ""),
            subtotal=calc["subtotal"],
            igv_amount=calc["igv_amount"],
            total=calc["total"],
        )
    return sales_document


@transaction.atomic
def issue_sales_document(sales_document_id) -> SalesDocument:
    """
    Emite el comprobante: asigna número correlativo con bloqueo pesimista.
    Valida unicidad (series + number). Cambia status a ISSUED.
    Si tiene sale_order → la marca INVOICED.
    """
    sales_document = SalesDocument.objects.select_for_update().get(pk=sales_document_id)
    if sales_document.status != "DRAFT":
        raise ValueError(
            f"Solo se pueden emitir comprobantes en Borrador. Estado actual: '{sales_document.status}'."
        )

    number = _next_series_number(sales_document.series)
    number_str = f"{number:08d}"

    # Verificar unicidad
    if SalesDocument.objects.filter(
        series=sales_document.series, number=number_str
    ).exclude(pk=sales_document.pk).exists():
        raise ValueError(
            f"Ya existe un comprobante con el número {sales_document.series_code}-{number_str}."
        )

    sales_document.number = number_str
    sales_document.status = "ISSUED"
    sales_document.save(update_fields=["number", "status"])

    if sales_document.sale_order_id:
        SaleOrder.objects.filter(pk=sales_document.sale_order_id).update(status="INVOICED")

    return sales_document


@transaction.atomic
def void_sales_document(sales_document_id, reason: str = "") -> SalesDocument:
    """Anula un comprobante ISSUED."""
    sales_document = SalesDocument.objects.select_for_update().get(pk=sales_document_id)
    if sales_document.status != "ISSUED":
        raise ValueError("Solo se pueden anular comprobantes emitidos.")
    sales_document.status = "VOIDED"
    if reason:
        sales_document.notes = (sales_document.notes + "\n" + reason).strip()
    sales_document.save(update_fields=["status", "notes"])
    return sales_document


@transaction.atomic
def cancel_sales_document(sales_document_id) -> SalesDocument:
    """Cancela un comprobante DRAFT."""
    sales_document = SalesDocument.objects.select_for_update().get(pk=sales_document_id)
    if sales_document.status != "DRAFT":
        raise ValueError("Solo se pueden cancelar comprobantes en Borrador.")
    sales_document.status = "CANCELLED"
    sales_document.save(update_fields=["status"])
    return sales_document


@transaction.atomic
def create_credit_note(
    sales_document_id,
    reason_code: str,
    reason_description: str,
    series: DocumentSeries,
    lines: list[dict] | None = None,
    created_by=None,
) -> SalesDocument:
    """
    Crea una nota de crédito (tipo 07) referenciando el comprobante original.
    Si no se pasan líneas, copia todas las del comprobante original.
    """
    original = SalesDocument.objects.select_related("customer", "store").get(pk=sales_document_id)
    if original.status != "ISSUED":
        raise ValueError("Solo se puede generar nota de crédito de comprobantes emitidos.")

    if lines is None:
        lines = [
            {
                "product": line.product,
                "description": line.description,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "unit_code": line.unit_code,
                "discount_amount": line.discount_amount,
                "tax_type": line.tax_type,
                "igv_rate": line.igv_rate,
                "sunat_product_code": line.sunat_product_code,
                "product_code": line.product_code,
            }
            for line in original.lines.all()
        ]

    note = create_sales_document_draft(
        store_id=str(original.store_id) if original.store_id else None,
        customer=original.customer,
        document_type="07",
        series=series,
        lines=lines,
        created_by=created_by,
        issue_date=timezone.now().date(),
        currency=original.currency,
        reference_document=original,
        reference_series=original.series_code,
        reference_number=original.number,
        note_reason_code=reason_code,
        note_reason_description=reason_description,
    )
    return note
