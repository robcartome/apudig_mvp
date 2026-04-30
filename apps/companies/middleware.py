class ActiveCompanyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.active_company_id = request.session.get("active_company_id")
        request.active_store_id = request.session.get("active_store_id")
        return self.get_response(request)
