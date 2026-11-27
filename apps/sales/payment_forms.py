from decimal import Decimal
from uuid import uuid4

from django import forms

from apps.pos.models import CashSession
from .models import MeansOfPayment


class SalesCollectionForm(forms.Form):
    cash_session = forms.ModelChoiceField(
        label="Sesión de caja", queryset=CashSession.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    means_of_payment = forms.ModelChoiceField(
        label="Medio de pago", queryset=MeansOfPayment.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    amount = forms.DecimalField(
        label="Importe a cobrar", max_digits=14, decimal_places=2, min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    operation_reference = forms.CharField(
        label="Referencia / número de operación", max_length=120, required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput)

    def __init__(self, *args, company_id, store_id, currency, balance, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cash_session"].queryset = CashSession.objects.filter(
            company_id=company_id, store_id=store_id, currency=currency,
            status=CashSession.Status.OPEN,
        ).select_related("register", "register__store")
        self.fields["means_of_payment"].queryset = MeansOfPayment.objects.filter(
            company_id=company_id, active=True,
        )
        self.fields["amount"].widget.attrs["max"] = balance
        self.initial.setdefault("amount", balance)
        self.initial.setdefault("idempotency_key", uuid4())
