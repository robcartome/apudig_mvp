"""
Comando: python manage.py seed

Crea datos iniciales (maestros + superusuario) para arrancar el proyecto desde cero.
"""

from django.core.management.base import BaseCommand

from apps.companies.models import Company, Store, UserCompanyAccess
from apps.inventory.models import Brand, Category, PriceList, Unit
from apps.partners.models import DocumentType
from apps.sales.models import BusinessDocumentType, DocumentSeries
from apps.users.models import Role, User, UserStore


UNITS = [
    ("NIU", "Unidad (bienes)"),
    ("ZZ", "Unidad (servicios)"),
    ("KGM", "Kilogramo"),
    ("MTR", "Metro"),
    ("LTR", "Litro"),
    ("BX", "Caja"),
    ("BG", "Bolsa"),
    ("SET", "Juego"),
    ("PK", "Paquete"),
    ("PZ", "Pieza"),
]

DOCUMENT_TYPES = [
    ("01", "DNI", "DNI"),
    ("06", "RUC", "RUC"),
    ("04", "Carnet de Extranjería", "CE"),
    ("07", "Pasaporte", "PAS"),
    ("A", "Cédula Diplomática", "CED"),
]

BUSINESS_DOC_TYPES = [
    {"code": "01", "name": "Factura", "category": "SALES", "is_sunat": True, "sunat_code": "01", "affects_stock": False},
    {"code": "03", "name": "Boleta de Venta", "category": "SALES", "is_sunat": True, "sunat_code": "03", "affects_stock": False},
    {"code": "07", "name": "Nota de Crédito", "category": "BILLING", "is_sunat": True, "sunat_code": "07", "affects_stock": False},
    {"code": "08", "name": "Nota de Débito", "category": "BILLING", "is_sunat": True, "sunat_code": "08", "affects_stock": False},
    {"code": "09", "name": "Guía de Remisión Remitente", "category": "LOGISTICS", "is_sunat": True, "sunat_code": "09", "affects_stock": True},
    {"code": "OV", "name": "Orden de Venta Interna", "category": "INTERNAL", "is_sunat": False, "sunat_code": "", "affects_stock": False},
    {"code": "COT", "name": "Cotización", "category": "INTERNAL", "is_sunat": False, "sunat_code": "", "affects_stock": False},
    {"code": "ENT", "name": "Entrada de Inventario", "category": "LOGISTICS", "is_sunat": False, "sunat_code": "", "affects_stock": True},
    {"code": "SAL", "name": "Salida de Inventario", "category": "LOGISTICS", "is_sunat": False, "sunat_code": "", "affects_stock": True},
    {"code": "TRF", "name": "Transferencia entre Almacenes", "category": "LOGISTICS", "is_sunat": False, "sunat_code": "", "affects_stock": True},
    {"code": "AJU", "name": "Ajuste de Inventario", "category": "LOGISTICS", "is_sunat": False, "sunat_code": "", "affects_stock": True},
]

ROLES = [
    ("ADMIN", "Administrador de empresa"),
    ("SUPERUSER", "Superusuario de sistema"),
    ("SELLER", "Vendedor"),
    ("CASHIER", "Cajero"),
    ("WAREHOUSE", "Almacenero"),
]

CATEGORIES = [
    # ("FERR", "Ferretería General"),
    # ("ELEC", "Eléctrico"),
    # ("PLOM", "Plomería"),
    # ("PINT", "Pintura"),
    # ("HERRA", "Herramientas"),
    # ("CONS", "Construcción"),
    # ("JARD", "Jardinería"),
    ("OTROS", "Otros"),
]

BRANDS = [
    "Akona", "Poelsan","GreenPlains", "GPA", "LUMO", "Rain", "Ranagua", "Cubull", "VALMAX", "C&A","KNAUF", "Stanley", "Makita", "Bosch", "3M", "Truper",
    "Black & Decker", "Dewalt""Sin Marca",
]


class Command(BaseCommand):
    help = "Carga datos iniciales (maestros) para arranque del proyecto"

    def add_arguments(self, parser):
        parser.add_argument("--email", default="admin@apudig.com", help="Email del superusuario")
        parser.add_argument("--password", default="admin1234", help="Contraseña del superusuario")
        parser.add_argument("--company", default="FERRETERÍA DEMO S.A.C.", help="Nombre de la empresa demo")
        parser.add_argument("--ruc", default="20000000001", help="RUC de la empresa demo")

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("=== SEED APUDIG MVP ==="))

        self._seed_units()
        self._seed_doc_types()
        self._seed_biz_doc_types()
        self._seed_categories()
        self._seed_brands()
        self._seed_price_lists()
        self._seed_roles()
        company, store = self._seed_company(options["company"], options["ruc"])
        user = self._seed_superuser(options["email"], options["password"])
        self._seed_user_access(user, company, store)
        self._seed_document_series(company, store)

        self.stdout.write(self.style.SUCCESS("\n✅ Seed completado."))
        self.stdout.write(f"   Login: {options['email']} / {options['password']}")
        self.stdout.write(f"   URL:   http://127.0.0.1:8000/login/")

    # ── helpers ──────────────────────────────────────────────────────────

    def _seed_units(self):
        created = 0
        for code, name in UNITS:
            _, ok = Unit.objects.get_or_create(code=code, defaults={"name": name})
            if ok:
                created += 1
        self.stdout.write(f"  Unidades:             {created} creadas / {len(UNITS)} total")

    def _seed_doc_types(self):
        created = 0
        for code, name, abbr in DOCUMENT_TYPES:
            _, ok = DocumentType.objects.get_or_create(code=code, defaults={"name": name, "abbreviation": abbr})
            if ok:
                created += 1
        self.stdout.write(f"  Tipos documento ID:   {created} creados / {len(DOCUMENT_TYPES)} total")

    def _seed_biz_doc_types(self):
        created = 0
        for d in BUSINESS_DOC_TYPES:
            _, ok = BusinessDocumentType.objects.get_or_create(code=d["code"], defaults=d)
            if ok:
                created += 1
        self.stdout.write(f"  Tipos doc. negocio:   {created} creados / {len(BUSINESS_DOC_TYPES)} total")

    def _seed_categories(self):
        created = 0
        for code, name in CATEGORIES:
            _, ok = Category.objects.get_or_create(code=code, defaults={"name": name})
            if ok:
                created += 1
        self.stdout.write(f"  Categorías:           {created} creadas / {len(CATEGORIES)} total")

    def _seed_brands(self):
        created = 0
        for name in BRANDS:
            _, ok = Brand.objects.get_or_create(name=name)
            if ok:
                created += 1
        self.stdout.write(f"  Marcas:               {created} creadas / {len(BRANDS)} total")

    def _seed_price_lists(self):
        lists = [
            ("PRECIO LISTA", "Precio estándar de lista"),
            ("PRECIO POR MAYOR", "Precio mayorista"),
            ("PRECIO DISTRIBUCION", "Precio para clientes especiales"),
        ]
        created = 0
        for name, desc in lists:
            _, ok = PriceList.objects.get_or_create(name=name, defaults={"description": desc})
            if ok:
                created += 1
        self.stdout.write(f"  Listas de precios:    {created} creadas / {len(lists)} total")

    def _seed_roles(self):
        created = 0
        for name, desc in ROLES:
            _, ok = Role.objects.get_or_create(name=name, defaults={"description": desc})
            if ok:
                created += 1
        self.stdout.write(f"  Roles:                {created} creados / {len(ROLES)} total")

    def _seed_company(self, name: str, ruc: str):
        company, ok = Company.objects.get_or_create(ruc=ruc, defaults={"name": name})
        if ok:
            self.stdout.write(f"  Empresa:              creada ({name})")
        else:
            self.stdout.write(f"  Empresa:              ya existe ({name})")

        store, ok = Store.objects.get_or_create(
            company=company, name="SEDE PRINCIPAL", defaults={"address": "Av. Demo 123", "active": True}
        )
        if ok:
            self.stdout.write("  Sucursal:             creada (SEDE PRINCIPAL)")
        return company, store

    def _seed_superuser(self, email: str, password: str):
        user, created = User.objects.get_or_create(
            email=email,
            defaults={"name": "Administrador", "is_staff": True, "is_superuser": True},
        )
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(f"  Superusuario:         creado ({email})")
        else:
            self.stdout.write(f"  Superusuario:         ya existe ({email})")
        return user

    def _seed_user_access(self, user, company, store):
        UserCompanyAccess.objects.get_or_create(
            user=user, company=company, store=store, defaults={"is_default": True}
        )
        UserStore.objects.get_or_create(
            user=user, store=store, defaults={"role": "ADMIN"}
        )
        self.stdout.write("  Acceso usuario:       configurado")

    def _seed_document_series(self, company, store):
        series_data = [
            ("01", "F001"),   # Factura
            ("03", "B001"),   # Boleta
            ("07", "FC01"),   # Nota crédito
            ("08", "FD01"),   # Nota débito
            ("COT", "C001"),  # Cotización
            ("OV", "O001"),   # Orden venta
            ("NV", "NV01"),   # Nota venta (interno, no SUNAT)
        ]
        created = 0
        for vtype, series in series_data:
            _, ok = DocumentSeries.objects.get_or_create(
                company=company, voucher_type=vtype, series=series,
                defaults={"store": store, "current_number": 0}
            )
            if ok:
                created += 1
        self.stdout.write(f"  Series doc.:          {created} creadas / {len(series_data)} total")
