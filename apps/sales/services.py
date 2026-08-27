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

from apps.core.models import AuditLog
from apps.inventory.models import MovementOrigin, ProductUnit, StockByWarehouse
from apps.inventory.services import confirm_movement, register_entry, register_exit
from apps.partners.models import DocumentType

from .models import (
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


def _reserve_quotation_number(series, requested_number=None, exclude_pk=None):
    """Reserva o valida un correlativo de cotización bajo bloqueo de serie."""
    if series is None or not series.active:
        raise ValueError("Debe seleccionar una serie documental activa.")
    locked_series = DocumentSeries.objects.select_for_update().get(pk=series.pk)
    number = int(requested_number) if requested_number else locked_series.current_number + 1
    duplicate = SalesQuotation.objects.filter(series=locked_series, number=number)
    if exclude_pk:
        duplicate = duplicate.exclude(pk=exclude_pk)
    if duplicate.exists():
        raise ValueError(
            f"Ya existe la cotización {locked_series.series}-{number:08d}."
        )
    if number > locked_series.current_number:
        locked_series.current_number = number
        locked_series.save(update_fields=["current_number"])
    return locked_series, number

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
    document_type = DocumentType.objects.get(code=document_type)
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


def _normalize_line_uom(line: dict) -> dict:
    """Valida la presentación del producto y congela su conversión a stock."""
    normalized = dict(line)
    product = normalized["product"]
    requested_unit = normalized.get("unit") or normalized.get("unit_id")
    conversions = ProductUnit.objects.select_related("unit").filter(product=product, active=True)
    if requested_unit:
        unit_id = getattr(requested_unit, "pk", requested_unit)
        conversion = conversions.filter(unit_id=unit_id).first()
        if conversion is None:
            raise ValueError(f"La unidad seleccionada no está habilitada para {product.name}.")
    else:
        conversion = conversions.filter(unit_id=product.unit_id).first()
        if conversion is None:
            conversion = ProductUnit.objects.create(
                product=product,
                unit=product.unit,
                conversion_factor=1,
                is_default_sale=True,
                is_default_purchase=True,
            )
    factor = Decimal(str(conversion.conversion_factor))
    normalized.update({
        "unit": conversion.unit,
        "unit_code": conversion.unit.code,
        "conversion_factor": factor,
        "stock_quantity": Decimal(str(normalized["quantity"])) * factor,
    })
    return normalized


def _normalize_lines_uom(lines):
    return [_normalize_line_uom(line) for line in lines]



@transaction.atomic
def create_quotation(store_id: str, customer, series: DocumentSeries, lines: list[dict], created_by=None, **kwargs) -> SalesQuotation:
    """
    Crea una cotización, asigna número de serie y calcula totales.
    lines: lista de dict con claves: product, description, quantity,
           unit_price, discount_amount (opcional), tax_type (opcional),
           igv_rate (opcional), memo (opcional).
    """
    requested_number = kwargs.pop("number", None)
    series, number = _reserve_quotation_number(series, requested_number)

    lines = _normalize_lines_uom(lines)
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
            unit=raw["unit"], unit_code=raw["unit_code"],
            conversion_factor=raw["conversion_factor"], stock_quantity=raw["stock_quantity"],
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

    series = kwargs.pop("series", quotation.series)
    requested_number = kwargs.pop("number", quotation.number)
    series, number = _reserve_quotation_number(
        series, requested_number, exclude_pk=quotation.pk
    )
    quotation.series = series
    quotation.series_code = series.series
    quotation.number = number

    for attr, value in kwargs.items():
        setattr(quotation, attr, value)

    lines = _normalize_lines_uom(lines)
    calculated_lines = [_calculate_line(l) for l in lines]
    subtotal = sum(l["subtotal"] for l in calculated_lines)
    igv_total = sum(l["igv_amount"] for l in calculated_lines)
    total_discount = sum(l.get("discount_amount", Decimal("0")) for l in lines)
    total = subtotal + igv_total

    quotation.subtotal = subtotal
    quotation.igv_total = igv_total
    quotation.total_discount = total_discount
    quotation.total = total
    quotation.save(update_fields=list(kwargs.keys()) + [
        "series", "series_code", "number", "subtotal", "igv_total",
        "total_discount", "total",
    ])

    quotation.lines.all().delete()
    for raw, calc in zip(lines, calculated_lines):
        SalesQuotationLine.objects.create(
            quotation=quotation,
            product=raw["product"],
            description=raw.get("description", ""),
            quantity=raw["quantity"],
            unit_price=raw["unit_price"],
            unit=raw["unit"], unit_code=raw["unit_code"],
            conversion_factor=raw["conversion_factor"], stock_quantity=raw["stock_quantity"],
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

    lines = _normalize_lines_uom(lines)
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
            unit=raw["unit"], unit_code=raw["unit_code"],
            conversion_factor=raw["conversion_factor"], stock_quantity=raw["stock_quantity"],
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
            "unit": line.unit_id,
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

    lines = _normalize_lines_uom(lines)
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
            unit=raw["unit"], unit_code=raw["unit_code"],
            conversion_factor=raw["conversion_factor"], stock_quantity=raw["stock_quantity"],
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
    """Calcula los totales tributarios sin confiar en importes del navegador."""
    taxable = Decimal("0")
    exempt = Decimal("0")
    unaffected = Decimal("0")
    export = Decimal("0")
    free = Decimal("0")
    igv_total = Decimal("0")
    total_discount = Decimal("0")

    for raw, calc in zip(lines, calculated):
        tax_type = raw.get("tax_type", "10")
        if tax_type == "10":
            taxable += calc["subtotal"]
        elif tax_type == "20":
            exempt += calc["subtotal"]
        elif tax_type == "30":
            unaffected += calc["subtotal"]
        elif tax_type == "40":
            export += calc["subtotal"]
        elif tax_type == "11":
            free += calc["subtotal"]
        else:
            raise ValueError(f"Tipo de IGV no soportado: '{tax_type}'.")
        igv_total += calc["igv_amount"]
        total_discount += Decimal(str(raw.get("discount_amount", 0)))

    subtotal = taxable + exempt + unaffected + export
    return {
        "subtotal": subtotal,
        "taxable_amount": taxable,
        "exempt_amount": exempt,
        "unaffected_amount": unaffected,
        "export_amount": export,
        "free_amount": free,
        "igv_total": igv_total,
        "total_discount": total_discount,
        "total": (subtotal + igv_total).quantize(Decimal("0.01")),
    }


def _validate_sales_document_input(store_id, customer, document_type, series, lines) -> None:
    if not store_id:
        raise ValueError("La sucursal es obligatoria.")
    if customer is None:
        raise ValueError("El cliente es obligatorio.")
    if not document_type:
        raise ValueError("El tipo de documento es obligatorio.")
    if not isinstance(document_type, DocumentType):
        document_type = DocumentType.objects.get(code=document_type)
    if series is None:
        raise ValueError("La serie es obligatoria.")
    if str(series.store_id) != str(store_id) or series.document_type_id != document_type.id:
        raise ValueError("La serie no corresponde a la sucursal y tipo de documento.")
    if str(customer.company_id) != str(series.company_id):
        raise ValueError("El cliente no pertenece a la empresa activa.")
    if not lines:
        raise ValueError("El documento debe tener al menos una línea.")
    return document_type


def _replace_sales_document_lines(document: SalesDocument, lines, calculated_lines) -> None:
    document.lines.all().delete()
    for raw, calc in zip(lines, calculated_lines):
        SalesDocumentLine.objects.create(
            sales_document=document,
            product=raw["product"],
            description=raw.get("description", ""),
            quantity=raw["quantity"],
            unit_price=raw["unit_price"],
            unit=raw["unit"], unit_code=raw["unit_code"],
            conversion_factor=raw["conversion_factor"], stock_quantity=raw["stock_quantity"],
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


def _inventory_lines_for_document(document: SalesDocument) -> list[dict]:
    """Agrupa únicamente productos configurados para controlar existencias."""
    grouped = {}
    lines = document.lines.select_related("product").filter(product__tracks_inventory=True)
    for line in lines:
        product_id = line.product_id
        if product_id not in grouped:
            grouped[product_id] = {
                "product_id": product_id,
                "quantity": Decimal("0"),
                "unit_price": line.unit_price,
            }
        grouped[product_id]["quantity"] += line.stock_quantity
    return list(grouped.values())


def _audit_sales_document(document, action: str, user=None, **metadata) -> None:
    AuditLog.objects.create(
        user=user,
        action=action,
        entity="SalesDocument",
        entity_id=str(document.pk),
        meta_data={
            "store_id": str(document.store_id) if document.store_id else None,
            "document_type": document.document_type.code,
            "status": document.status,
            "series": document.series_code,
            "number": document.number,
            **metadata,
        },
    )


def _validate_stock_for_sale(document: SalesDocument, lines: list[dict]) -> None:
    if not document.warehouse_id:
        raise ValueError("Debe seleccionar un almacén antes de emitir el documento.")
    if document.warehouse.store_id != document.store_id:
        raise ValueError("El almacén no pertenece a la sucursal del documento.")
    if document.warehouse.allow_negative_stock:
        return

    for line in lines:
        stock, _ = StockByWarehouse.objects.select_for_update().get_or_create(
            product_id=line["product_id"],
            warehouse_id=document.warehouse_id,
            defaults={"quantity": Decimal("0")},
        )
        required = Decimal(str(line["quantity"]))
        if stock.quantity < required:
            raise ValueError(
                f"Stock insuficiente para {stock.product}. "
                f"Disponible: {stock.quantity}; requerido: {required}."
            )


def _register_sale_inventory_exit(document: SalesDocument):
    if not document.register_inventory_movement:
        return None
    if document.inventory_movement_id:
        return document.inventory_movement

    lines = _inventory_lines_for_document(document)
    if not lines:
        return None
    _validate_stock_for_sale(document, lines)
    movement = register_exit(
        store_id=str(document.store_id),
        warehouse_id=str(document.warehouse_id),
        date=timezone.now(),
        lines=lines,
        created_by=document.created_by,
        origin=MovementOrigin.SALE,
        customer=document.customer,
        series=document.series_code,
        number=document.number,
        reference_doc=str(document.pk),
        reason="Venta",
        description=f"Salida por documento {document.series_code}-{document.number}",
    )
    return confirm_movement(movement, confirmed_by=document.created_by)


def _register_sale_inventory_reversal(document: SalesDocument):
    original = document.inventory_movement
    if original is None:
        return None
    if hasattr(original, "reversal"):
        return original.reversal

    lines = [
        {
            "product_id": detail.product_id,
            "quantity": detail.quantity,
            "unit_price": detail.unit_price,
        }
        for detail in original.details.all()
    ]
    movement = register_entry(
        store_id=str(document.store_id),
        warehouse_id=str(original.warehouse_id),
        date=timezone.now(),
        lines=lines,
        created_by=document.created_by,
        origin=MovementOrigin.SALE_REVERSAL,
        reversal_of=original,
        customer=document.customer,
        series=document.series_code,
        number=document.number,
        reference_doc=str(document.pk),
        reason="Anulación de venta",
        description=f"Reversión de {document.series_code}-{document.number}",
    )
    return confirm_movement(movement, confirmed_by=document.created_by)


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
    document_type = _validate_sales_document_input(store_id, customer, document_type, series, lines)
    lines = _normalize_lines_uom(lines)
    calculated_lines = [_calculate_line(line) for line in lines]
    totals = _calc_sales_document_totals(lines, calculated_lines)
    requested_number = kwargs.pop("number", "")

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
        number=requested_number,
        sale_order=sale_order,
        created_by=created_by,
        **{k: v for k, v in {**totals, **kwargs}.items()},
    )
    _replace_sales_document_lines(sales_document, lines, calculated_lines)
    _audit_sales_document(sales_document, "CREATE", created_by)
    return sales_document


@transaction.atomic
def copy_sales_document(sales_document_id, copied_by=None) -> SalesDocument:
    """Copia un documento como borrador, sin correlativo ni relaciones de origen."""
    source = (
        SalesDocument.objects.select_for_update()
        .select_related("customer", "document_type", "series")
        .prefetch_related("lines__product")
        .get(pk=sales_document_id)
    )
    if source.customer is None:
        raise ValueError("No se puede copiar un documento cuyo cliente fue eliminado.")
    if source.series is None or not source.series.active:
        raise ValueError("No se puede copiar el documento porque su serie no está activa.")

    lines = [
        {
            "product": line.product,
            "description": line.description,
            "quantity": line.quantity,
            "unit_price": line.unit_price,
            "unit": line.unit_id,
            "unit_code": line.unit_code,
            "discount_amount": line.discount_amount,
            "tax_type": line.tax_type,
            "igv_rate": line.igv_rate,
            "sunat_product_code": line.sunat_product_code,
            "product_code": line.product_code,
            "memo": line.memo,
        }
        for line in source.lines.all()
    ]
    copied = create_sales_document_draft(
        store_id=str(source.store_id),
        customer=source.customer,
        document_type=source.document_type,
        series=source.series,
        lines=lines,
        created_by=copied_by,
        issue_date=timezone.now().date(),
        currency=source.currency,
        exchange_rate=source.exchange_rate,
        payment_method=source.payment_method,
        means_of_payment=source.means_of_payment,
        seller=source.seller,
        price_list=source.price_list,
        register_inventory_movement=source.register_inventory_movement,
        warehouse=source.warehouse,
        notes=source.notes,
        internal_reference=source.internal_reference,
    )
    _audit_sales_document(
        copied, "COPY", copied_by, source_document_id=str(source.pk)
    )
    return copied


@transaction.atomic
def delete_sales_document_draft(sales_document_id, deleted_by=None) -> None:
    """Elimina únicamente documentos que todavía se encuentran en borrador."""
    document = SalesDocument.objects.select_for_update().get(pk=sales_document_id)
    if document.status != "DRAFT":
        raise ValueError("Solo se pueden eliminar documentos en Borrador.")
    _audit_sales_document(document, "DELETE", deleted_by)
    document.delete()


@transaction.atomic
def create_document_from_quotation(
    quotation_id,
    *,
    document_type: str,
    series: DocumentSeries,
    created_by=None,
    register_inventory_movement=True,
    warehouse=None,
) -> SalesDocument:
    """Convierte una cotización aprobada en un único borrador de venta."""
    if not isinstance(document_type, DocumentType):
        document_type = DocumentType.objects.get(code=document_type)
    quotation = SalesQuotation.objects.select_for_update().get(pk=quotation_id)
    if quotation.status != "APPROVED":
        raise ValueError("Solo se pueden convertir cotizaciones aprobadas.")
    if SalesDocument.objects.filter(source_quotation=quotation).exists():
        raise ValueError("La cotización ya fue convertida en un documento de venta.")
    if quotation.store_id is None:
        raise ValueError("La cotización no tiene una sucursal válida.")
    if (
        not series.active
        or series.document_type_id != document_type.id
        or series.company_id != quotation.store.company_id
        or series.store_id != quotation.store_id
    ):
        raise ValueError("La serie no corresponde a la cotización y tipo seleccionados.")
    if register_inventory_movement and warehouse is None:
        raise ValueError("Debe seleccionar un almacén para registrar el movimiento.")
    if warehouse is not None and warehouse.store_id != quotation.store_id:
        raise ValueError("El almacén no pertenece a la sucursal de la cotización.")

    lines = [
        {
            "product": line.product,
            "description": line.description,
            "quantity": line.quantity,
            "unit_price": line.unit_price,
            "unit": line.unit_id,
            "unit_code": line.unit_code,
            "discount_amount": line.discount_amount,
            "tax_type": line.tax_type,
            "igv_rate": line.igv_rate,
            "sunat_product_code": line.sunat_product_code,
            "product_code": line.product_code,
            "memo": line.memo,
        }
        for line in quotation.lines.select_related("product")
    ]
    document = create_sales_document_draft(
        store_id=str(quotation.store_id),
        customer=quotation.customer,
        document_type=document_type,
        series=series,
        lines=lines,
        created_by=created_by,
        issue_date=timezone.now().date(),
        currency=quotation.currency,
        exchange_rate=quotation.exchange_rate,
        payment_method=quotation.payment_method,
        means_of_payment=quotation.means_of_payment,
        notes=quotation.notes,
        internal_reference=quotation.internal_reference,
        source_quotation=quotation,
        register_inventory_movement=register_inventory_movement,
        warehouse=warehouse,
    )
    _audit_sales_document(
        document,
        "CREATE_FROM_QUOTATION",
        created_by,
        source_quotation_id=str(quotation.pk),
    )
    return document


@transaction.atomic
def update_sales_document_draft(
    sales_document_id, *, customer, series, lines, updated_by=None, **kwargs
) -> SalesDocument:
    """Actualiza cabecera y líneas, exclusivamente mientras el documento sea borrador."""
    document = SalesDocument.objects.select_for_update().get(pk=sales_document_id)
    if document.status != "DRAFT":
        raise ValueError("Solo se pueden editar documentos en Borrador.")

    store_id = kwargs.get("store_id", document.store_id)
    document_type = kwargs.get("document_type", document.document_type)
    document_type = _validate_sales_document_input(store_id, customer, document_type, series, lines)
    lines = _normalize_lines_uom(lines)
    calculated_lines = [_calculate_line(line) for line in lines]
    totals = _calc_sales_document_totals(lines, calculated_lines)
    requested_number = kwargs.pop("number", "")

    document.customer = customer
    document.customer_document_type = customer.document_type
    document.customer_document_number = customer.document_number
    document.customer_legal_name = customer.legal_name
    document.customer_address = getattr(customer, "address", "")
    document.customer_ubigeo = getattr(customer, "ubigeo", "")
    document.series = series
    document.series_code = series.series
    document.number = requested_number
    for field, value in {**kwargs, **totals}.items():
        setattr(document, field, value)
    document.save()
    _replace_sales_document_lines(document, lines, calculated_lines)
    _audit_sales_document(document, "UPDATE", updated_by)
    return document


@transaction.atomic
def issue_sales_document(sales_document_id, issued_by=None) -> SalesDocument:
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
    if sales_document.series is None or not sales_document.series.active:
        raise ValueError("La serie documental no está activa.")
    if (
        sales_document.series.store_id != sales_document.store_id
        or sales_document.series.document_type_id != sales_document.document_type_id
    ):
        raise ValueError("La serie no corresponde a la sucursal y tipo del documento.")
    if not sales_document.lines.exists():
        raise ValueError("El documento debe tener al menos una línea para ser emitido.")

    locked_series = DocumentSeries.objects.select_for_update().get(pk=sales_document.series_id)
    if sales_document.number:
        number = int(sales_document.number)
        number_str = f"{number:08d}"
        if number > locked_series.current_number:
            locked_series.current_number = number
            locked_series.save(update_fields=["current_number"])
    else:
        locked_series.current_number += 1
        locked_series.save(update_fields=["current_number"])
        number_str = f"{locked_series.current_number:08d}"

    # Verificar unicidad
    if SalesDocument.objects.filter(
        series=sales_document.series, number=number_str
    ).exclude(pk=sales_document.pk).exists():
        raise ValueError(
            f"Ya existe un comprobante con el número {sales_document.series_code}-{number_str}."
        )

    sales_document.number = number_str
    inventory_movement = _register_sale_inventory_exit(sales_document)
    sales_document.inventory_movement = inventory_movement
    sales_document.status = "ISSUED"
    sales_document.save(update_fields=["number", "inventory_movement", "status"])
    _audit_sales_document(
        sales_document,
        "ISSUE",
        issued_by or sales_document.created_by,
        inventory_movement_id=(
            str(inventory_movement.pk) if inventory_movement is not None else None
        ),
    )

    if sales_document.sale_order_id:
        SaleOrder.objects.filter(pk=sales_document.sale_order_id).update(status="INVOICED")

    return sales_document


@transaction.atomic
def void_sales_document(sales_document_id, reason: str = "", voided_by=None) -> SalesDocument:
    """Anula un comprobante ISSUED."""
    sales_document = SalesDocument.objects.select_for_update().get(pk=sales_document_id)
    if sales_document.status != "ISSUED":
        raise ValueError("Solo se pueden anular comprobantes emitidos.")
    reversal = _register_sale_inventory_reversal(sales_document)
    sales_document.status = "VOIDED"
    if reason:
        sales_document.notes = (sales_document.notes + "\n" + reason).strip()
    sales_document.save(update_fields=["status", "notes"])
    _audit_sales_document(
        sales_document,
        "VOID",
        voided_by or sales_document.created_by,
        reason=reason,
        inventory_reversal_id=str(reversal.pk) if reversal is not None else None,
    )
    return sales_document


@transaction.atomic
def cancel_sales_document(sales_document_id, cancelled_by=None) -> SalesDocument:
    """Cancela un comprobante DRAFT."""
    sales_document = SalesDocument.objects.select_for_update().get(pk=sales_document_id)
    if sales_document.status != "DRAFT":
        raise ValueError("Solo se pueden cancelar comprobantes en Borrador.")
    sales_document.status = "CANCELLED"
    sales_document.save(update_fields=["status"])
    _audit_sales_document(
        sales_document, "CANCEL", cancelled_by or sales_document.created_by
    )
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
    if (
        not series.active
        or series.document_type.code != "07"
        or series.company_id != original.store.company_id
        or series.store_id != original.store_id
    ):
        raise ValueError("La serie de nota de crédito no corresponde al documento original.")

    if lines is None:
        lines = [
            {
                "product": line.product,
                "description": line.description,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "unit": line.unit_id,
                "unit_code": line.unit_code,
                "discount_amount": line.discount_amount,
                "tax_type": line.tax_type,
                "igv_rate": line.igv_rate,
                "sunat_product_code": line.sunat_product_code,
                "product_code": line.product_code,
                "memo": line.memo,
            }
            for line in original.lines.all()
        ]

    note = create_sales_document_draft(
        store_id=str(original.store_id) if original.store_id else None,
        customer=original.customer,
        document_type=DocumentType.objects.get(code="07"),
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
        register_inventory_movement=False,
    )
    _audit_sales_document(
        note,
        "CREATE_CREDIT_NOTE",
        created_by,
        reference_document_id=str(original.pk),
        reason_code=reason_code,
    )
    return note
