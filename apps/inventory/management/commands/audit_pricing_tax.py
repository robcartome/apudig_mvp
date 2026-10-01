from django.core.management.base import BaseCommand
from django.db.models import Count, F, Q

from apps.inventory.models import MovementDetail, PriceList, Product, ProductPrice


class Command(BaseCommand):
    help = "Audita la clasificacion de precios, impuestos y costos historicos sin modificar datos."

    def handle(self, *args, **options):
        products = Product.objects.all()
        legacy_movements = MovementDetail.objects.filter(
            cost_source=MovementDetail.CostSource.LEGACY
        )
        duplicate_defaults = (
            PriceList.objects.filter(is_default=True)
            .values("company_id")
            .annotate(total=Count("id"))
            .filter(total__gt=1)
        )
        cross_company_prices = ProductPrice.objects.exclude(
            Q(price_list__company_id=F("product__company_id"))
        ).count()

        rows = {
            "products": products.count(),
            "taxed_products": products.filter(tax_affectation="10").count(),
            "products_without_sale_price": products.filter(price_sale__lte=0).count(),
            "products_without_inventory_cost": products.filter(inventory_unit_cost__lte=0).count(),
            "legacy_movement_details": legacy_movements.count(),
            "companies_with_multiple_default_lists": duplicate_defaults.count(),
            "cross_company_product_prices": cross_company_prices,
        }
        for key, value in rows.items():
            self.stdout.write(f"{key}: {value}")
        if rows["legacy_movement_details"]:
            self.stdout.write(self.style.WARNING(
                "Los movimientos LEGACY requieren revision historica; no se convierten automaticamente."
            ))
