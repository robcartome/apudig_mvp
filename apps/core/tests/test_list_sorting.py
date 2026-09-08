from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase

from apps.core.list_filters import sort_queryset


class RecordingQuerySet:
    def __init__(self):
        self.ordering = ()

    def order_by(self, *fields):
        self.ordering = fields
        return self


class ListSortingTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_sort_queryset_uses_only_whitelisted_fields_and_stable_pk(self):
        request = self.factory.get("/", {"sort": "total", "dir": "asc"})
        queryset = RecordingQuerySet()

        result, state = sort_queryset(
            request,
            queryset,
            {"date": "created_at", "total": ("currency", "total")},
            default=("date", "desc"),
        )

        self.assertIs(result, queryset)
        self.assertEqual(queryset.ordering, ("currency", "total", "pk"))
        self.assertEqual(state, {"key": "total", "direction": "asc"})

    def test_invalid_sort_parameters_fall_back_to_safe_default(self):
        request = self.factory.get("/", {"sort": "supplier__password", "dir": "sideways"})
        queryset = RecordingQuerySet()

        _, state = sort_queryset(
            request,
            queryset,
            {"date": ("issue_date", "created_at")},
            default=("date", "desc"),
        )

        self.assertEqual(queryset.ordering, ("-issue_date", "-created_at", "-pk"))
        self.assertEqual(state, {"key": "date", "direction": "desc"})

    def test_sortable_header_preserves_filters_and_removes_page(self):
        request = self.factory.get(
            "/", {"q": "tornillo", "status": "DRAFT", "page": "3", "sort": "date", "dir": "asc"}
        )
        template = Template(
            '{% load list_sorting %}{% sortable_header "date" "Fecha" %}'
        )

        html = template.render(Context({
            "request": request,
            "table_sort": {"key": "date", "direction": "asc"},
        }))

        self.assertIn("q=tornillo", html)
        self.assertIn("status=DRAFT", html)
        self.assertIn("sort=date", html)
        self.assertIn("dir=desc", html)
        self.assertNotIn("page=3", html)
        self.assertIn('aria-sort="ascending"', html)
