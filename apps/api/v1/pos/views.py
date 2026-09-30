from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.api.v1.base import BaseCompanyAPIView
from apps.inventory import selectors as inventory_selectors
from apps.inventory.models import Category, PriceList, Product, ProductPrice, ProductUnit, StockByWarehouse, Unit, Warehouse
from apps.inventory.pricing import split_final_price, tax_rate_for_company
from apps.core.models import AuditLog
from apps.partners.models import Customer
from apps.pos import selectors
from apps.pos.models import CashSession, PosRegister, PosReturn, PosTransaction
from apps.pos.permissions import POS_PERMISSION_DEFINITIONS
from apps.pos.services import (
    PosDomainError,
    cancel_pos_draft,
    checkout_pos_sale,
    close_cash_session,
    create_consolidated_invoice,
    issue_pos_debit_note,
    open_cash_session,
    register_cash_movement,
    register_credit_collection,
    refund_pos_transaction,
    request_consolidated_invoice,
    void_pos_transaction,
)
from apps.sales.models import SalesDocument
from apps.users.permissions import user_can_access_context, user_has_company_permission

from .serializers import (
    CashMovementRequestSerializer,
    CashSessionCloseRequestSerializer,
    CashSessionOpenRequestSerializer,
    CashSessionSerializer,
    CreditCollectionRequestSerializer,
    ConsolidatedInvoiceRequestSerializer,
    InvoiceTicketRequestSerializer,
    PosCheckoutRequestSerializer,
    PosCustomerCreateRequestSerializer,
    PosProductCreateRequestSerializer,
    PosDebitNoteRequestSerializer,
    PosRegisterSerializer,
    PosReprintRequestSerializer,
    PosReturnRequestSerializer,
    PosReturnSerializer,
    PosTransactionSerializer,
    PosVoidRequestSerializer,
)


class PosAPIView(BaseCompanyAPIView):
    company_required = True
    permission_classes = [permissions.IsAuthenticated]

    def get_store_id(self):
        if isinstance(self.request.auth, dict) and self.request.auth.get("store_id"):
            return self.request.auth["store_id"]
        raw_request = getattr(self.request, "_request", None)
        if raw_request is not None:
            store_id = getattr(raw_request, "active_store_id", None)
            if store_id:
                return store_id
            session = getattr(raw_request, "session", None)
            if session is not None:
                return session.get("active_store_id")
        return None

    def get_pos_context(self):
        company_id = self.get_company_id()
        store_id = self.get_store_id()
        if not company_id or not store_id:
            raise PermissionDenied("Debe seleccionar una empresa y sucursal para operar el POS.")
        if not user_can_access_context(self.request.user, company_id, store_id):
            raise PermissionDenied("No tiene acceso a la empresa o sucursal activa.")
        return str(company_id), str(store_id)

    def require_pos_permission(self, permission_code):
        company_id, store_id = self.get_pos_context()
        if not user_has_company_permission(
            self.request.user,
            company_id,
            permission_code,
            store_id,
        ):
            raise PermissionDenied(f"No tiene el permiso {permission_code}.")
        return company_id, store_id

    def handle_exception(self, exc):
        if isinstance(exc, PosDomainError):
            return Response(
                {"code": exc.code, "detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if isinstance(exc, DjangoValidationError):
            detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", [str(exc)])
            return Response(
                {"code": "VALIDATION_ERROR", "detail": detail},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if isinstance(exc, ObjectDoesNotExist):
            return Response(
                {"code": "NOT_FOUND", "detail": "El recurso solicitado no existe."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if isinstance(exc, IntegrityError):
            return Response(
                {"code": "CONFLICT", "detail": "La operacion entra en conflicto con datos existentes."},
                status=status.HTTP_409_CONFLICT,
            )
        return super().handle_exception(exc)


class PosBootstrapAPIView(PosAPIView):
    @extend_schema(
        tags=["POS"],
        summary="Obtener configuracion operativa del POS",
        parameters=[OpenApiParameter(name="register_id", type=str, required=False)],
    )
    def get(self, request):
        company_id, store_id = self.require_pos_permission("read.pos")
        registers = selectors.get_pos_registers(company_id=company_id, store_id=store_id)
        register_id = request.query_params.get("register_id")
        selected_register = None
        open_session = None
        if register_id:
            selected_register = get_object_or_404(registers, pk=register_id)
            open_session = selectors.get_open_session(
                company_id=company_id,
                store_id=store_id,
                register_id=selected_register.pk,
            )
        suggested_opening_totals = {"PEN": "0.00", "USD": "0.00"}
        if selected_register:
            for currency in suggested_opening_totals:
                previous = CashSession.objects.filter(
                    register=selected_register, status=CashSession.Status.CLOSED,
                    currency=currency, next_opening_total__isnull=False,
                ).order_by("-closed_at").values_list("next_opening_total", flat=True).first()
                if previous is not None:
                    suggested_opening_totals[currency] = str(previous)

        means = selectors.get_pos_means_of_payment(company_id=company_id)
        series = selectors.get_pos_document_series(company_id=company_id, store_id=store_id)
        price_lists = PriceList.objects.filter(company_id=company_id, active=True).order_by(
            "-is_default", "name"
        )
        categories = Category.objects.filter(company_id=company_id, active=True).annotate(
            product_count=Count("products", filter=Q(products__active=True))
        ).filter(product_count__gt=0).order_by("name")
        product_categories = Category.objects.filter(
            company_id=company_id, active=True
        ).order_by("name")
        permission_codes = [f"{action}.{module}" for action, module, _ in POS_PERMISSION_DEFINITIONS]
        granted_permissions = [
            code
            for code in permission_codes
            if user_has_company_permission(request.user, company_id, code, store_id)
        ]
        return Response({
            "registers": PosRegisterSerializer(registers, many=True).data,
            "selected_register": (
                PosRegisterSerializer(selected_register).data if selected_register else None
            ),
            "open_session": (
                CashSessionSerializer(open_session).data if open_session else None
            ),
            "suggested_opening_totals": suggested_opening_totals,
            "means_of_payment": [
                {
                    "id": str(item.pk),
                    "name": item.name,
                    "kind": item.kind,
                    "requires_reference": item.requires_reference,
                }
                for item in means
            ],
            "payment_methods": [
                {
                    "id": str(item.pk),
                    "name": item.name,
                    "is_cash": item.is_cash,
                    "receives_change": item.receives_change,
                    "immediate_payment": item.immediate_payment,
                    "is_credit": item.is_credit,
                    "allows_advance": item.allows_advance,
                    "credit_days": item.credit_days,
                }
                for item in selectors.get_pos_payment_methods(company_id=company_id)
            ],
            "document_series": [
                {
                    "id": str(item.pk),
                    "document_type": item.document_type.code,
                    "series": item.series,
                    "next_number": item.current_number + 1,
                }
                for item in series
            ],
            "price_lists": [
                {
                    "id": str(item.pk),
                    "name": item.name,
                    "is_default": item.is_default,
                }
                for item in price_lists
            ],
            "categories": [
                {
                    "id": str(item.pk),
                    "name": item.name,
                    "product_count": item.product_count,
                }
                for item in categories
            ],
            "product_categories": [
                {"id": str(item.pk), "name": item.name}
                for item in product_categories
            ],
            "units": [
                {"id": str(item.pk), "code": item.code, "name": item.name}
                for item in Unit.objects.all().order_by("code")
            ],
            "readiness": {
                "registers": registers.count(),
                "products": Product.objects.filter(company_id=company_id, active=True).count(),
                "warehouses": Warehouse.objects.filter(store_id=store_id, active=True).count(),
                "customers": Customer.objects.filter(company_id=company_id, active=True).count(),
                "series": series.count(),
                "means_of_payment": means.count(),
            },
            "permissions": granted_permissions,
        })


class PosProductSearchAPIView(PosAPIView):
    @extend_schema(
        tags=["POS"],
        summary="Buscar productos con precio y stock de la caja",
        parameters=[
            OpenApiParameter(name="register_id", type=str, required=True),
            OpenApiParameter(name="search", type=str, required=False),
            OpenApiParameter(name="currency", type=str, required=False),
            OpenApiParameter(name="price_list_id", type=str, required=False),
            OpenApiParameter(name="category_id", type=str, required=False),
            OpenApiParameter(name="product_ids", type=str, required=False),
        ],
    )
    def get(self, request):
        company_id, store_id = self.require_pos_permission("read.pos")
        register_id = request.query_params.get("register_id")
        if not register_id:
            raise ValidationError({"register_id": "Seleccione una caja."})
        register = get_object_or_404(
            selectors.get_pos_registers(company_id=company_id, store_id=store_id),
            pk=register_id,
        )
        currency = (request.query_params.get("currency") or "PEN").upper()
        if currency not in {"PEN", "USD"}:
            raise ValidationError({"currency": "La moneda debe ser S/. o $."})
        search = (request.query_params.get("search") or "").strip()
        product_ids = [
            value.strip()
            for value in (request.query_params.get("product_ids") or "").split(",")
            if value.strip()
        ]
        if len(product_ids) > 100:
            raise ValidationError({"product_ids": "Puede consultar hasta 100 productos."})
        products_query = inventory_selectors.search_products(
            search,
            company_id=company_id,
            active_only=True,
        )
        if product_ids:
            products_query = products_query.filter(pk__in=product_ids)
        category_id = request.query_params.get("category_id")
        if category_id:
            category = get_object_or_404(
                Category.objects.filter(company_id=company_id, active=True),
                pk=category_id,
            )
            products_query = products_query.filter(category_id=category.pk)
        products = list(products_query[:30])
        product_ids = [product.pk for product in products]
        requested_price_list_id = request.query_params.get("price_list_id")
        price_list_id = register.default_price_list_id
        if requested_price_list_id:
            price_list = get_object_or_404(
                PriceList.objects.filter(company_id=company_id, active=True),
                pk=requested_price_list_id,
            )
            if (
                price_list.pk != register.default_price_list_id
                and not user_has_company_permission(
                    request.user, company_id, "change.pos.pricelist", store_id
                )
            ):
                raise PermissionDenied("No tiene permiso para cambiar la lista de precios.")
            price_list_id = price_list.pk
        list_prices = {}
        if price_list_id:
            list_prices = {
                str(row.product_id): row.amount
                for row in ProductPrice.objects.filter(
                    product_id__in=product_ids,
                    price_list_id=price_list_id,
                    currency=currency,
                    active=True,
                )
            }
        conversion_rows = list(
            ProductUnit.objects.filter(
                product_id__in=product_ids,
                active=True,
            ).select_related("unit", "product__unit")
        )
        base_unit_prices = {
            str(row.product_id): row.sale_price
            for row in conversion_rows
            if row.sale_price is not None and row.unit_id == row.product.unit_id
        }
        conversions_by_product = {}
        for conversion in conversion_rows:
            conversions_by_product.setdefault(str(conversion.product_id), []).append(conversion)
        stock_by_product = {}
        if register.default_warehouse_id:
            stock_by_product = {
                str(row.product_id): row.quantity
                for row in StockByWarehouse.objects.filter(
                    product_id__in=product_ids,
                    warehouse_id=register.default_warehouse_id,
                )
            }
        result = []
        for product in products:
            product_id = str(product.pk)
            base_price = list_prices.get(product_id)
            has_list_price = base_price is not None
            if currency == "PEN" and base_price is None:
                base_price = base_unit_prices.get(product_id, product.price_sale)
            units = []
            product_tax_rate = tax_rate_for_company(
                company_id, affectation_type=product.tax_affectation
            )
            for conversion in conversions_by_product.get(product_id, []):
                commercial_price = (
                    conversion.sale_price
                    if currency == "PEN" and conversion.sale_price is not None and not has_list_price
                    else (
                        base_price * conversion.conversion_factor
                        if base_price is not None else None
                    )
                )
                unit_price = (
                    split_final_price(
                        commercial_price,
                        affectation_type=product.tax_affectation,
                        tax_rate=product_tax_rate,
                    ).unit_value
                    if commercial_price is not None else None
                )
                units.append({
                    "id": str(conversion.unit_id),
                    "code": conversion.unit.code,
                    "name": conversion.unit.name,
                    "conversion_factor": str(conversion.conversion_factor),
                    "unit_price": str(unit_price) if unit_price is not None else None,
                    "is_default_sale": conversion.is_default_sale,
                })
            if not any(item["id"] == str(product.unit_id) for item in units):
                base_unit_value = (
                    split_final_price(
                        base_price,
                        affectation_type=product.tax_affectation,
                        tax_rate=product_tax_rate,
                    ).unit_value
                    if base_price is not None else None
                )
                units.append({
                    "id": str(product.unit_id),
                    "code": product.unit.code,
                    "name": product.unit.name,
                    "conversion_factor": "1.000000",
                    "unit_price": str(base_unit_value) if base_unit_value is not None else None,
                    "is_default_sale": not any(item["is_default_sale"] for item in units),
                })
            units.sort(key=lambda item: (not item["is_default_sale"], item["code"]))
            selected_unit = units[0]
            result.append({
                "id": product_id,
                "sku": product.sku,
                "barcode": product.barcode,
                "name": product.name,
                "category_id": str(product.category_id) if product.category_id else None,
                "category": product.category.name if product.category_id else "Sin categoría",
                "unit_id": selected_unit["id"],
                "unit": selected_unit["code"],
                "unit_price": selected_unit["unit_price"],
                "units": units,
                "tax_type": product.tax_affectation,
                "igv_rate": str(product_tax_rate),
                "stock": str(stock_by_product.get(str(product.pk), 0)),
                "stock_unit": product.unit.code,
                "tracks_inventory": product.tracks_inventory,
                "image": product.image,
            })
        return Response(result)


class PosProductCommercialAPIView(PosAPIView):
    @extend_schema(tags=["POS"], summary="Consultar precios y stock de un producto POS")
    def get(self, request, product_id):
        company_id, store_id = self.require_pos_permission("read.pos")
        product = get_object_or_404(
            Product.objects.select_related("unit", "category").filter(
                company_id=company_id, active=True
            ),
            pk=product_id,
        )
        prices = ProductPrice.objects.filter(
            product=product, price_list__company_id=company_id,
            price_list__active=True, active=True,
        ).select_related("price_list").order_by("-price_list__is_default", "price_list__name")
        warehouses = Warehouse.objects.filter(
            store__company_id=company_id, active=True
        ).select_related("store").order_by("store__name", "name")
        stock_map = {
            str(row.warehouse_id): row.quantity
            for row in StockByWarehouse.objects.filter(
                product=product, warehouse_id__in=warehouses.values("pk")
            )
        }
        return Response({
            "product": {
                "id": str(product.pk), "sku": product.sku, "name": product.name,
                "unit": product.unit.code, "tracks_inventory": product.tracks_inventory,
            },
            "prices": [
                {
                    "price_list_id": str(item.price_list_id),
                    "name": item.price_list.name,
                    "currency": item.currency,
                    "amount": str(item.amount),
                    "price_includes_tax": item.price_list.prices_include_tax,
                    "is_default": item.price_list.is_default,
                }
                for item in prices
            ],
            "base_price": {
                "currency": "PEN",
                "amount": str(product.price_sale),
                "price_includes_tax": True,
            },
            "warehouses": [
                {
                    "id": str(item.pk), "store": item.store.name,
                    "warehouse": item.name,
                    "quantity": str(stock_map.get(str(item.pk), Decimal("0.000"))),
                    "is_current": str(item.store_id) == str(store_id),
                }
                for item in warehouses
            ],
        })


class PosProductCreateAPIView(PosAPIView):
    @extend_schema(tags=["POS"], summary="Registrar producto rápido desde el POS", request=PosProductCreateRequestSerializer)
    def post(self, request):
        company_id, store_id = self.require_pos_permission("create.pos.product")
        serializer = PosProductCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        unit = get_object_or_404(Unit.objects.all(), pk=data["unit_id"])
        category = None
        if data.get("category_id"):
            category = get_object_or_404(
                Category.objects.filter(company_id=company_id, active=True),
                pk=data["category_id"],
            )
        if Product.objects.filter(company_id=company_id, sku__iexact=data["sku"]).exists():
            raise ValidationError({"sku": "Ya existe un producto con este código."})
        if data.get("barcode") and Product.objects.filter(
            company_id=company_id, barcode=data["barcode"]
        ).exists():
            raise ValidationError({"barcode": "Ya existe un producto con este código de barras."})
        price = data["sale_price"]
        tax_type = data["tax_type"]
        rate = tax_rate_for_company(company_id, affectation_type=tax_type)
        commercial_price = price
        if not data["includes_tax"] and tax_type == "10":
            commercial_price = price * (Decimal("1") + rate / Decimal("100"))
        with transaction.atomic():
            product = Product.objects.create(
                company_id=company_id, name=data["name"], sku=data["sku"],
                barcode=data.get("barcode", ""), unit=unit, category=category,
                price_sale=commercial_price.quantize(Decimal("0.01")),
                tax_affectation=tax_type,
                tracks_inventory=data["tracks_inventory"], active=True,
            )
            ProductUnit.objects.create(
                product=product, unit=unit, conversion_factor=1,
                sale_price=commercial_price, is_default_sale=True,
                is_default_purchase=True, active=True,
            )
            AuditLog.objects.create(
                user=request.user, action="CREATE", entity="Product", entity_id=str(product.pk),
                meta_data={"source": "POS", "store_id": str(store_id), "sku": product.sku},
            )
        return Response({"id": str(product.pk)}, status=status.HTTP_201_CREATED)


class CashSessionOpenAPIView(PosAPIView):
    @extend_schema(tags=["POS"], summary="Abrir caja", request=CashSessionOpenRequestSerializer)
    def post(self, request):
        company_id, store_id = self.require_pos_permission("open.pos.cash")
        serializer = CashSessionOpenRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        register = get_object_or_404(
            PosRegister.objects.filter(
                company_id=company_id,
                store_id=store_id,
                active=True,
            ),
            pk=data["register_id"],
        )
        session = open_cash_session(
            register_id=register.pk,
            opened_by=request.user,
            opening_total=data["opening_total"],
            denominations=data.get("denominations"),
            note=data.get("note", ""),
            currency=data["currency"],
        )
        return Response(CashSessionSerializer(session).data, status=status.HTTP_201_CREATED)


class CashMovementAPIView(PosAPIView):
    @extend_schema(tags=["POS"], summary="Registrar movimiento de caja", request=CashMovementRequestSerializer)
    def post(self, request, session_id):
        company_id, store_id = self.require_pos_permission("manage.pos.cash_movements")
        cash_session = get_object_or_404(
            CashSession.objects.filter(company_id=company_id, store_id=store_id),
            pk=session_id,
        )
        serializer = CashMovementRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        can_authorize_movement = user_has_company_permission(
            request.user,
            company_id,
            "authorize.pos.cash_movement",
            store_id,
        )
        movement = register_cash_movement(
            cash_session_id=cash_session.pk,
            movement_type=data["movement_type"],
            amount=data["amount"],
            description=data["description"],
            reason_code=data.get("reason_code", ""),
            created_by=request.user,
            authorized_by=request.user if can_authorize_movement else None,
        )
        return Response({
            "id": str(movement.pk),
            "movement_type": movement.movement_type,
            "amount": str(movement.amount),
            "description": movement.description,
            "created_at": movement.created_at,
            "drawer_cash_after": str(movement.drawer_cash_after),
        }, status=status.HTTP_201_CREATED)


class CashSessionSummaryAPIView(PosAPIView):
    @extend_schema(tags=["POS"], summary="Consultar resumen operativo de caja")
    def get(self, request, session_id):
        company_id, store_id = self.require_pos_permission("read.pos")
        cash_session = get_object_or_404(
            CashSession.objects.select_related("register", "opened_by").filter(
                company_id=company_id,
                store_id=store_id,
            ),
            pk=session_id,
        )
        summary = selectors.get_cash_session_summary(cash_session)
        movement_details = cash_session.cash_movements.select_related(
            "created_by"
        ).order_by("-created_at")
        session_sales = cash_session.transactions.select_related(
            "sales_document__customer", "sales_document__document_type"
        ).order_by("-completed_at", "-created_at")
        return Response({
            "session": CashSessionSerializer(cash_session).data,
            "opening_total": str(summary["opening_total"]),
            "payment_total": str(summary["payment_total"]),
            "refund_total": str(summary["refund_total"]),
            "cash_sales": str(summary["cash_sales"]),
            "non_cash_sales": str(summary["non_cash_sales"]),
            "cash_in": str(summary["cash_in"]),
            "cash_out": str(summary["cash_out"]),
            "expected_cash_total": str(summary["expected_cash_total"]),
            "payments": [
                {
                    "means_of_payment_id": str(row["means_of_payment_id"]),
                    "name": row["means_of_payment__name"],
                    "kind": row["means_of_payment__kind"],
                    "expected_amount": str(row["total"]),
                    "gross_amount": str(row["gross_total"]),
                    "refund_amount": str(row["refund_total"]),
                    "counted_amount": (
                        str(row["counted_amount"])
                        if row["counted_amount"] is not None else None
                    ),
                    "difference": (
                        str(row["difference"])
                        if row["difference"] is not None else None
                    ),
                    "operations": row["operations"],
                }
                for row in summary["payments"]
            ],
            "movements": [
                {
                    "movement_type": row["movement_type"],
                    "total": str(row["total"]),
                    "operations": row["operations"],
                }
                for row in summary["movements"]
            ],
            "movement_details": [
                {
                    "id": str(item.pk),
                    "movement_type": item.movement_type,
                    "movement_type_label": item.get_movement_type_display(),
                    "amount": str(item.amount),
                    "reason_code": item.reason_code,
                    "description": item.description,
                    "created_at": item.created_at,
                    "created_by": (
                        item.created_by.display_name if item.created_by_id else "Sistema"
                    ),
                }
                for item in movement_details
            ],
            "sales": [
                {
                    "id": str(item.pk),
                    "document": (
                        f"{item.sales_document.series_code}-{item.sales_document.number}"
                    ),
                    "customer": item.sales_document.customer_legal_name,
                    "total": str(item.sales_document.total),
                    "currency": item.sales_document.currency,
                    "status": item.status,
                    "completed_at": item.completed_at,
                }
                for item in session_sales
            ],
            "transactions": summary["transactions"],
            "can_close": summary["can_close"],
        })


class CashSessionCloseAPIView(PosAPIView):
    @extend_schema(tags=["POS"], summary="Cerrar caja", request=CashSessionCloseRequestSerializer)
    def post(self, request, session_id):
        company_id, store_id = self.require_pos_permission("close.pos.cash")
        cash_session = get_object_or_404(
            CashSession.objects.filter(company_id=company_id, store_id=store_id),
            pk=session_id,
        )
        serializer = CashSessionCloseRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        can_authorize_difference = user_has_company_permission(
            request.user,
            company_id,
            "authorize.pos.cash_difference",
            store_id,
        )
        session = close_cash_session(
            cash_session_id=cash_session.pk,
            closed_by=request.user,
            counted_cash_total=data["counted_cash_total"],
            denominations=data.get("denominations"),
            next_opening_total=data["next_opening_total"],
            safe_deposit_total=data.get("safe_deposit_total"),
            bank_deposit_total=data.get("bank_deposit_total", 0),
            bank_deposit_destination=data.get("bank_deposit_destination", ""),
            note=data.get("note", ""),
            tender_counts=data.get("tender_counts"),
            difference_authorized_by=request.user if can_authorize_difference else None,
        )
        return Response(CashSessionSerializer(session).data)


class CreditCollectionAPIView(PosAPIView):
    @extend_schema(tags=["POS"], summary="Listar ventas a credito con saldo")
    def get(self, request):
        company_id, store_id = self.require_pos_permission("manage.pos.collections")
        cash_session = get_object_or_404(
            CashSession.objects.filter(
                company_id=company_id, store_id=store_id, status=CashSession.Status.OPEN
            ),
            pk=request.query_params.get("cash_session_id"),
        )
        transactions = selectors.get_credit_sales_with_balance(
            company_id=company_id,
            store_id=store_id,
            search=request.query_params.get("search", ""),
        ).filter(sales_document__currency=cash_session.currency)[:50]
        return Response([
            {
                "transaction_id": str(item.pk),
                "sales_document_id": str(item.sales_document_id),
                "document": f"{item.sales_document.series_code}-{item.sales_document.number}",
                "customer": item.sales_document.customer_legal_name,
                "customer_document": item.sales_document.customer_document_number,
                "currency": item.sales_document.currency,
                "total": str(item.sales_document.total),
                "collected_total": str(item.collected_total),
                "outstanding_total": str(item.outstanding_total),
                "due_date": item.sales_document.due_date,
            }
            for item in transactions
        ])

    @extend_schema(tags=["POS"], summary="Registrar cobranza de credito", request=CreditCollectionRequestSerializer)
    def post(self, request):
        company_id, store_id = self.require_pos_permission("manage.pos.collections")
        serializer = CreditCollectionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        cash_session = get_object_or_404(
            CashSession.objects.filter(
                company_id=company_id, store_id=store_id, status=CashSession.Status.OPEN
            ),
            pk=data["cash_session_id"],
        )
        payment = register_credit_collection(
            sales_document_id=data["sales_document_id"],
            cash_session_id=cash_session.pk,
            means_of_payment_id=data["means_of_payment_id"],
            amount=data["amount"],
            amount_in_sale_currency=data["amount"],
            received_amount=data.get("received_amount", data["amount"]),
            change_amount=Decimal("0.00"),
            operation_reference=data.get("operation_reference", ""),
            idempotency_key=data["idempotency_key"],
            created_by=request.user,
        )
        transaction_record = payment.sales_document.pos_transaction
        paid_total = payment.sales_document.pos_payments.filter(
            status="REGISTERED"
        ).aggregate(total=Sum("amount_in_sale_currency"))["total"] or Decimal("0.00")
        return Response({
            "id": str(payment.pk),
            "purpose": payment.purpose,
            "payment_status": transaction_record.payment_status,
            "paid_total": str(paid_total),
            "outstanding_total": str(payment.sales_document.total - paid_total),
        }, status=status.HTTP_201_CREATED)


class PosCheckoutAPIView(PosAPIView):
    @extend_schema(tags=["POS"], summary="Registrar venta POS", request=PosCheckoutRequestSerializer)
    def post(self, request):
        company_id, store_id = self.require_pos_permission("sell.pos")
        serializer = PosCheckoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["document_type"] in {"01", "03"} and not user_has_company_permission(
            request.user, company_id, "issue.pos.invoice", store_id
        ):
            raise PermissionDenied("No tiene permiso para emitir comprobantes desde el POS.")
        if data["payment_condition"] == "CREDIT" and not user_has_company_permission(
            request.user, company_id, "sell.pos.credit", store_id
        ):
            raise PermissionDenied("No tiene permiso para registrar ventas a credito.")

        transaction_record, created = checkout_pos_sale(
            company_id=company_id,
            store_id=store_id,
            register_id=data["register_id"],
            cash_session_id=data["cash_session_id"],
            idempotency_key=data["idempotency_key"],
            document_type_code=data["document_type"],
            series_id=data["series_id"],
            customer_id=data.get("customer_id"),
            payment_condition=data["payment_condition"],
            payment_method_id=data.get("payment_method_id"),
            due_date=data.get("due_date"),
            warehouse_id=data.get("warehouse_id"),
            price_list_id=data.get("price_list_id"),
            currency=data["currency"],
            exchange_rate=data["exchange_rate"],
            global_discount_amount=data["global_discount_amount"],
            global_discount_before_tax=data["global_discount_before_tax"],
            notes=data.get("notes", ""),
            device_identifier=data.get("device_identifier", ""),
            line_items=data["lines"],
            payment_items=data["payments"],
            cashier=request.user,
            allow_price_change=user_has_company_permission(
                request.user, company_id, "change.pos.price", store_id
            ),
            allow_discount=user_has_company_permission(
                request.user, company_id, "apply.pos.discount", store_id
            ),
            allow_pricelist_change=user_has_company_permission(
                request.user, company_id, "change.pos.pricelist", store_id
            ),
        )
        payload = PosTransactionSerializer(transaction_record).data
        payload["created"] = created
        return Response(
            payload,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PosDraftAPIView(PosAPIView):
    @extend_schema(tags=["POS"], summary="Guardar o actualizar venta POS en borrador", request=PosCheckoutRequestSerializer)
    def post(self, request):
        company_id, store_id = self.require_pos_permission("sell.pos")
        serializer = PosCheckoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["document_type"] in {"01", "03"} and not user_has_company_permission(
            request.user, company_id, "issue.pos.invoice", store_id
        ):
            raise PermissionDenied("No tiene permiso para preparar ese comprobante desde el POS.")
        if data["payment_condition"] == "CREDIT" and not user_has_company_permission(
            request.user, company_id, "sell.pos.credit", store_id
        ):
            raise PermissionDenied("No tiene permiso para preparar ventas a credito.")
        transaction_record, created = checkout_pos_sale(
            company_id=company_id,
            store_id=store_id,
            register_id=data["register_id"],
            cash_session_id=data["cash_session_id"],
            idempotency_key=data["idempotency_key"],
            document_type_code=data["document_type"],
            series_id=data["series_id"],
            customer_id=data.get("customer_id"),
            payment_condition=data["payment_condition"],
            payment_method_id=data.get("payment_method_id"),
            due_date=data.get("due_date"),
            warehouse_id=data.get("warehouse_id"),
            price_list_id=data.get("price_list_id"),
            currency=data["currency"],
            exchange_rate=data["exchange_rate"],
            global_discount_amount=data["global_discount_amount"],
            global_discount_before_tax=data["global_discount_before_tax"],
            notes=data.get("notes", ""),
            device_identifier=data.get("device_identifier", ""),
            line_items=data["lines"],
            payment_items=[],
            cashier=request.user,
            allow_price_change=user_has_company_permission(
                request.user, company_id, "change.pos.price", store_id
            ),
            allow_discount=user_has_company_permission(
                request.user, company_id, "apply.pos.discount", store_id
            ),
            allow_pricelist_change=user_has_company_permission(
                request.user, company_id, "change.pos.pricelist", store_id
            ),
            save_as_draft=True,
        )
        payload = PosTransactionSerializer(transaction_record).data
        payload["created"] = created
        return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class PosDraftCancelAPIView(PosAPIView):
    @extend_schema(tags=["POS"], summary="Descartar venta POS en borrador")
    def post(self, request, transaction_id):
        company_id, store_id = self.require_pos_permission("sell.pos")
        record = get_object_or_404(
            PosTransaction.objects.filter(company_id=company_id, store_id=store_id),
            pk=transaction_id,
        )
        record = cancel_pos_draft(pos_transaction_id=record.pk, cancelled_by=request.user)
        return Response(PosTransactionSerializer(record).data)


class PosTransactionDetailAPIView(PosAPIView):
    @extend_schema(tags=["POS"], summary="Consultar ticket POS")
    def get(self, request, transaction_id):
        company_id, store_id = self.require_pos_permission("read.pos")
        record = get_object_or_404(
            PosTransaction.objects.filter(
                company_id=company_id,
                store_id=store_id,
            ).select_related(
                "sales_document__document_type",
                "sales_document__customer",
                "sales_document__store__company",
                "cash_session",
                "register",
                "cashier",
            ).prefetch_related(
                "sales_document__lines",
                "sales_document__pos_payments__means_of_payment",
            ),
            pk=transaction_id,
        )
        return Response(PosTransactionSerializer(record).data)


class RecentPosTransactionsAPIView(PosAPIView):
    @extend_schema(
        tags=["POS"],
        summary="Listar comprobantes POS recientes para reimpresion",
        parameters=[
            OpenApiParameter(name="register_id", type=str, required=False),
            OpenApiParameter(name="cash_session_id", type=str, required=False),
            OpenApiParameter(name="scope", type=str, required=False),
            OpenApiParameter(name="date", type=str, required=False),
        ],
    )
    def get(self, request):
        company_id, store_id = self.require_pos_permission("reprint.pos.receipt")
        scope = request.query_params.get("scope", "all")
        if scope not in {"session", "day", "all"}:
            raise ValidationError({"scope": "El alcance debe ser session, day o all."})
        cash_session_id = request.query_params.get("cash_session_id") if scope == "session" else None
        if scope == "session" and not cash_session_id:
            raise ValidationError({"cash_session_id": "La sesion es obligatoria para este filtro."})
        business_date = None
        if scope == "day":
            business_date = parse_date(request.query_params.get("date", "")) or timezone.localdate()
        records = selectors.get_recent_pos_transactions(
            company_id=company_id,
            store_id=store_id,
            register_id=request.query_params.get("register_id"),
            cash_session_id=cash_session_id,
            business_date=business_date,
        )
        return Response(PosTransactionSerializer(records, many=True).data)


class PosTransactionReprintAPIView(PosAPIView):
    @extend_schema(
        tags=["POS"],
        summary="Registrar y recuperar una reimpresion POS",
        request=PosReprintRequestSerializer,
    )
    def post(self, request, transaction_id):
        company_id, store_id = self.require_pos_permission("reprint.pos.receipt")
        serializer = PosReprintRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = get_object_or_404(
            selectors.get_recent_pos_transactions(
                company_id=company_id,
                store_id=store_id,
                limit=None,
            ),
            pk=transaction_id,
        )
        AuditLog.objects.create(
            user=request.user,
            action="REPRINT",
            entity="PosTransaction",
            entity_id=str(record.pk),
            meta_data={
                "width_mm": serializer.validated_data["width"],
                "sales_document_id": str(record.sales_document_id),
            },
        )
        payload = PosTransactionSerializer(record).data
        payload["print_width"] = serializer.validated_data["width"]
        return Response(payload)


class PosTransactionVoidAPIView(PosAPIView):
    @extend_schema(tags=["POS"], summary="Anular Nota de Venta POS", request=PosVoidRequestSerializer)
    def post(self, request, transaction_id):
        company_id, store_id = self.require_pos_permission("void.pos.sale")
        record = get_object_or_404(
            PosTransaction.objects.filter(company_id=company_id, store_id=store_id),
            pk=transaction_id,
        )
        serializer = PosVoidRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = void_pos_transaction(
            pos_transaction_id=record.pk,
            reason=serializer.validated_data["reason"],
            voided_by=request.user,
        )
        return Response(PosTransactionSerializer(record).data)


class PosTransactionReturnAPIView(PosAPIView):
    @extend_schema(
        tags=["POS"],
        summary="Registrar devolución total o parcial",
        request=PosReturnRequestSerializer,
        responses={201: PosReturnSerializer},
    )
    def post(self, request, transaction_id):
        company_id, store_id = self.require_pos_permission("refund.pos.sale")
        get_object_or_404(
            PosTransaction.objects.filter(company_id=company_id, store_id=store_id),
            pk=transaction_id,
        )
        serializer = PosReturnRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        get_object_or_404(
            CashSession.objects.filter(
                company_id=company_id,
                store_id=store_id,
                status=CashSession.Status.OPEN,
            ),
            pk=data["cash_session_id"],
        )
        pos_return, created = refund_pos_transaction(
            pos_transaction_id=transaction_id,
            cash_session_id=data["cash_session_id"],
            idempotency_key=data["idempotency_key"],
            line_items=data["lines"],
            refund_means_of_payment_id=data["refund_means_of_payment_id"],
            reason=data["reason"],
            reason_code=data["reason_code"],
            credit_note_series_id=data.get("credit_note_series_id"),
            operation_reference=data.get("operation_reference", ""),
            created_by=request.user,
        )
        pos_return = PosReturn.objects.select_related("credit_note").prefetch_related(
            "refund_payments__means_of_payment"
        ).get(pk=pos_return.pk)
        payload = PosReturnSerializer(pos_return).data
        payload["created"] = created
        return Response(
            payload,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PosTransactionDebitNoteAPIView(PosAPIView):
    @extend_schema(
        tags=["POS"],
        summary="Emitir Nota de Débito relacionada",
        request=PosDebitNoteRequestSerializer,
    )
    def post(self, request, transaction_id):
        company_id, store_id = self.require_pos_permission("issue.pos.invoice")
        get_object_or_404(
            PosTransaction.objects.filter(company_id=company_id, store_id=store_id),
            pk=transaction_id,
        )
        serializer = PosDebitNoteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        note, created = issue_pos_debit_note(
            pos_transaction_id=transaction_id,
            idempotency_key=data["idempotency_key"],
            series_id=data["series_id"],
            reason_code=data["reason_code"],
            reason=data["reason"],
            line_items=data["lines"],
            created_by=request.user,
        )
        return Response({
            "id": str(note.pk),
            "document_type": note.document_type.code,
            "series": note.series_code,
            "number": note.number,
            "status": note.status,
            "currency": note.currency,
            "total": str(note.total),
            "reference_document_id": str(note.reference_document_id),
            "created": created,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class InvoiceableTicketListAPIView(PosAPIView):
    @extend_schema(
        tags=["POS"],
        summary="Listar tickets consolidables",
        parameters=[
            OpenApiParameter(name="customer_id", type=str, required=False),
            OpenApiParameter(name="date", type=str, required=False),
        ],
    )
    def get(self, request):
        company_id, store_id = self.require_pos_permission("read.pos")
        business_date = None
        if request.query_params.get("date"):
            business_date = parse_date(request.query_params["date"])
            if business_date is None:
                raise ValidationError({"date": "Use el formato YYYY-MM-DD."})
        queryset = selectors.get_invoiceable_tickets(
            company_id=company_id,
            store_id=store_id,
            customer_id=request.query_params.get("customer_id"),
            business_date=business_date,
        )
        return Response(PosTransactionSerializer(queryset, many=True).data)


def _ensure_source_context(source_document_ids, company_id, store_id):
    unique_ids = {str(value) for value in source_document_ids}
    matching = PosTransaction.objects.filter(
        company_id=company_id,
        store_id=store_id,
        sales_document_id__in=unique_ids,
    ).count()
    if matching != len(unique_ids):
        raise SalesDocument.DoesNotExist


class InvoiceRequestAPIView(PosAPIView):
    @extend_schema(tags=["POS"], summary="Solicitar factura consolidada", request=InvoiceTicketRequestSerializer)
    def post(self, request):
        company_id, store_id = self.require_pos_permission("consolidate.pos.invoice")
        serializer = InvoiceTicketRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        source_ids = serializer.validated_data["source_document_ids"]
        _ensure_source_context(source_ids, company_id, store_id)
        transactions = request_consolidated_invoice(
            source_document_ids=source_ids,
            requested_by=request.user,
        )
        return Response(PosTransactionSerializer(transactions, many=True).data)


class ConsolidatedInvoiceAPIView(PosAPIView):
    @extend_schema(tags=["POS"], summary="Emitir factura consolidada", request=ConsolidatedInvoiceRequestSerializer)
    def post(self, request):
        company_id, store_id = self.require_pos_permission("consolidate.pos.invoice")
        if not user_has_company_permission(
            request.user, company_id, "issue.pos.invoice", store_id
        ):
            raise PermissionDenied("No tiene permiso para emitir facturas.")
        serializer = ConsolidatedInvoiceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        _ensure_source_context(data["source_document_ids"], company_id, store_id)
        invoice, links = create_consolidated_invoice(
            source_document_ids=data["source_document_ids"],
            invoice_series_id=data["invoice_series_id"],
            created_by=request.user,
        )
        return Response({
            "invoice_id": str(invoice.pk),
            "document_type": invoice.document_type.code,
            "series": invoice.series_code,
            "number": invoice.number,
            "status": invoice.status,
            "currency": invoice.currency,
            "total": str(invoice.total),
            "source_document_ids": [str(link.source_document_id) for link in links],
        }, status=status.HTTP_201_CREATED)


class PosCustomerCreateAPIView(PosAPIView):
    @extend_schema(
        tags=["POS"],
        summary="Buscar clientes para el POS",
        parameters=[OpenApiParameter(name="search", type=str, required=False)],
    )
    def get(self, request):
        company_id, _ = self.require_pos_permission("read.pos")
        search = (request.query_params.get("search") or "").strip()
        queryset = Customer.objects.filter(company_id=company_id, active=True)
        if search:
            queryset = queryset.filter(
                Q(document_number__icontains=search)
                | Q(legal_name__icontains=search)
                | Q(trade_name__icontains=search)
            )
        queryset = queryset.order_by("legal_name")[:30]
        return Response([
            {
                "id": str(customer.pk),
                "document_type": customer.document_type,
                "document_number": customer.document_number,
                "legal_name": customer.legal_name,
                "trade_name": customer.trade_name,
                "address": customer.address,
            }
            for customer in queryset
        ])

    @extend_schema(tags=["POS"], summary="Crear cliente rapido", request=PosCustomerCreateRequestSerializer)
    def post(self, request):
        company_id, _ = self.require_pos_permission("create.pos.customer")
        serializer = PosCustomerCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        customer, created = Customer.objects.get_or_create(
            company_id=company_id,
            document_type=data["document_type"],
            document_number=data["document_number"],
            defaults={
                "legal_name": data["legal_name"],
                "trade_name": data.get("trade_name", ""),
                "address": data.get("address", ""),
                "ubigeo": data.get("ubigeo", ""),
                "phone": data.get("phone", ""),
                "email": data.get("email", ""),
                "active": True,
            },
        )
        return Response({
            "id": str(customer.pk),
            "document_type": customer.document_type,
            "document_number": customer.document_number,
            "legal_name": customer.legal_name,
            "address": customer.address,
            "created": created,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
