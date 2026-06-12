from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response


class CatalogLegacyPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100

    def get_paginated_response(self, data):
        return Response(
            {
                "total": self.count,
                "limit": self.limit,
                "offset": self.offset,
                "results": data,
            }
        )
