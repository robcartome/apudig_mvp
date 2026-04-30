import uuid


def _validate_uuid(value) -> str | None:
    """Valida y normaliza un UUID de sesión; devuelve None si el valor es inválido."""
    if not value:
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError):
        return None


class ActiveCompanyMiddleware:
    """
    Inyecta active_company_id y active_store_id en cada request
    leyendo de la sesión. Valida que los valores sean UUIDs legítimos
    para prevenir inyección de sesión.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.active_company_id = _validate_uuid(request.session.get("active_company_id"))
        request.active_store_id = _validate_uuid(request.session.get("active_store_id"))
        return self.get_response(request)
