"""Discover branches using the current ERP tenant authorization."""
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.catalog.access import CatalogAccessMixin
from apps.companies.models import Store, UserCompanyAccess
from apps.users.models import UserStore


class MyAccessibleStoresAPIView(CatalogAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    require_product_permission = False

    def get(self, request):
        access = self.catalog_access
        stores = Store.objects.filter(company_id=access.company_id, active=True)
        if not access.can_view_private:
            # Both ERP membership and an active branch assignment must survive
            # revocation; stale JWT claims alone never authorize a branch.
            memberships = UserCompanyAccess.objects.filter(user=request.user, company_id=access.company_id)
            assignments = UserStore.objects.filter(user=request.user, is_active=True).values("store_id")
            stores = stores.filter(pk__in=assignments)
            if not memberships.filter(store__isnull=True).exists():
                stores = stores.filter(pk__in=memberships.values("store_id"))
        rows = list(stores.order_by("name", "pk").values("id", "name"))
        return Response({"store_ids": [str(row["id"]) for row in rows], "stores": rows})
