from django import forms
from .models import WebsiteDomain


class WebsiteDomainForm(forms.ModelForm):
    class Meta:
        model = WebsiteDomain
        fields = ("hostname", "kind")
        labels = {"hostname": "Dominio (sin https://, puerto ni ruta)", "kind": "Tipo"}
        widgets = {"hostname": forms.TextInput(attrs={"class": "form-control", "placeholder": "tienda.ejemplo.com"}), "kind": forms.Select(attrs={"class": "form-select"})}
