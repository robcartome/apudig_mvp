from django import forms
from django.template import Context, Template
from django.test import SimpleTestCase


class FormFeedbackTests(SimpleTestCase):
    def test_shared_summary_identifies_invalid_visible_and_hidden_fields(self):
        class ExampleForm(forms.Form):
            name = forms.CharField()
            customer = forms.CharField(widget=forms.HiddenInput())

        form = ExampleForm(data={})
        self.assertFalse(form.is_valid())
        html = Template(
            '{% include "components/form_errors_alert.html" with form=form %}'
            '{{ form.name }}'
        ).render(Context({"form": form}))
        self.assertIn('data-invalid-field="id_name"', html)
        self.assertIn('data-invalid-field="id_customer"', html)
        self.assertIn('aria-invalid="true"', html)

    def test_partner_picker_exposes_error_on_visible_control(self):
        class ExampleForm(forms.Form):
            customer = forms.CharField(widget=forms.HiddenInput())

        form = ExampleForm(data={})
        self.assertFalse(form.is_valid())
        html = Template(
            '{% include "components/partner_select.html" with field=form.customer %}'
        ).render(Context({"form": form}))
        self.assertIn('id="id_customer-picker"', html)
        self.assertIn('aria-invalid="true"', html)
