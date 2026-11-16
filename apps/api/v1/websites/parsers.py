from io import BytesIO

from rest_framework.exceptions import APIException, ParseError
from rest_framework.parsers import JSONParser, MultiPartParser
from django.conf import settings

from apps.websites.documents import DOCUMENT_MAX_BYTES


class PayloadTooLarge(APIException):
    status_code = 413
    default_detail = "La solicitud supera el límite permitido."
    default_code = "PAYLOAD_TOO_LARGE"


class WebsiteJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        body = stream.read(DOCUMENT_MAX_BYTES + 1)
        if len(body) > DOCUMENT_MAX_BYTES:
            raise PayloadTooLarge()
        try:
            return super().parse(BytesIO(body), media_type, parser_context)
        except RecursionError as exc:
            raise ParseError("La estructura JSON es demasiado profunda.") from exc


class BoundedUploadStream:
    def __init__(self, stream, limit):
        self.stream, self.remaining = stream, limit

    def read(self, size=-1):
        size = min(size, self.remaining + 1) if size >= 0 else self.remaining + 1
        value = self.stream.read(size)
        self.remaining -= len(value)
        if self.remaining < 0:
            raise PayloadTooLarge()
        return value

    def readline(self, size=-1):
        size = min(size, self.remaining + 1) if size >= 0 else self.remaining + 1
        value = self.stream.readline(size)
        self.remaining -= len(value)
        if self.remaining < 0:
            raise PayloadTooLarge()
        return value


class WebsiteMultipartParser(MultiPartParser):
    def parse(self, stream, media_type=None, parser_context=None):
        return super().parse(BoundedUploadStream(stream, settings.PRODUCT_IMAGE_MAX_SIZE + 64 * 1024), media_type, parser_context)
