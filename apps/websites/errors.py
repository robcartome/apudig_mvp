"""Domain errors preserve HTTP-independent codes and field paths."""


class WebsiteError(Exception):
    def __init__(self, message, *, code="VALIDATION", fields=None, status=400):
        super().__init__(message)
        self.code = code
        self.fields = fields or {}
        self.status = status


def invalid_document(fields):
    return WebsiteError("Revisa los campos indicados.", fields=fields)
