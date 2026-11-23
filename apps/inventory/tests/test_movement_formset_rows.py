from django.test import SimpleTestCase

from apps.inventory.forms import MovementDetailEditFormSet, MovementDetailFormSet


class MovementFormsetRowsTest(SimpleTestCase):
    def test_new_movement_starts_with_one_line(self):
        formset = MovementDetailFormSet(prefix="lines")
        self.assertEqual(formset.total_form_count(), 1)
        self.assertEqual(formset.management_form.initial["TOTAL_FORMS"], 1)

    def test_existing_lines_are_preserved_without_extra_blank_lines(self):
        initial = [{"quantity": "1"}, {"quantity": "2"}]
        for formset_class in (MovementDetailFormSet, MovementDetailEditFormSet):
            with self.subTest(formset=formset_class):
                formset = formset_class(prefix="lines", initial=initial)
                self.assertEqual(formset.total_form_count(), 2)
                self.assertEqual([form.initial["quantity"] for form in formset], ["1", "2"])
