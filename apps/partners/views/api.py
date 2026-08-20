import json

from django.db import IntegrityError
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.companies.models import Company

from ..forms import CustomerForm, SupplierForm


def _company(request):
    company_id = getattr(request, "active_company_id", None) or request.session.get("active_company_id")
    return Company.objects.filter(pk=company_id).first() if company_id else None


def _payload(request):
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None


@require_POST
def customer_quick_create(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "No autorizado."}, status=401)
    company = _company(request)
    if company is None:
        return JsonResponse({"error": "Debe seleccionar una empresa."}, status=400)
    data = _payload(request)
    if data is None:
        return JsonResponse({"error": "Datos inválidos."}, status=400)
    form = CustomerForm({
        "document_type": data.get("document_type"),
        "document_number": data.get("document_number"),
        "legal_name": data.get("name"),
        "trade_name": "",
        "address": data.get("address", ""),
        "phone": "",
        "email": "",
        "active": True,
    }, company=company)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    try:
        customer = form.save()
    except IntegrityError:
        return JsonResponse({
            "errors": {"document_number": [{"message": "Ya existe un cliente con ese documento."}]}
        }, status=400)
    return JsonResponse({
        "id": str(customer.pk),
        "text": f"{customer.document_number} — {customer.legal_name}",
        "address": customer.address,
    }, status=201)


@require_POST
def supplier_quick_create(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "No autorizado."}, status=401)
    company = _company(request)
    if company is None:
        return JsonResponse({"error": "Debe seleccionar una empresa."}, status=400)
    data = _payload(request)
    if data is None:
        return JsonResponse({"error": "Datos inválidos."}, status=400)
    form = SupplierForm({
        "name": data.get("name"),
        "document_number": data.get("document_number"),
        "address": data.get("address", ""),
        "phone": "",
        "email": "",
        "contact_name": "",
        "active": True,
    }, company=company)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    try:
        supplier = form.save()
    except IntegrityError:
        return JsonResponse({
            "errors": {"document_number": [{"message": "Ya existe un proveedor con ese documento."}]}
        }, status=400)
    return JsonResponse({
        "id": str(supplier.pk),
        "text": f"{supplier.document_number} — {supplier.name}",
        "address": supplier.address,
    }, status=201)
