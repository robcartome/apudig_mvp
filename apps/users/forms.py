from django import forms
from django.contrib.auth import get_user_model

from apps.companies.models import Company, CompanyBranding, Store
from .models import Permission, Role, UserOperationalFlags

User = get_user_model()


class UserCreateForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta:
        model = User
        fields = ("email", "name", "phone", "is_staff", "is_active")

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Ya existe un usuario con este correo.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("email", "name", "phone", "is_staff", "is_active")

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        qs = User.objects.filter(email=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe un usuario con este correo.")
        return email


class SetPasswordForm(forms.Form):
    password1 = forms.CharField(
        label="Nueva contraseña",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        min_length=8,
    )
    password2 = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        return cleaned


class UserOperationalFlagsForm(forms.ModelForm):
    class Meta:
        model = UserOperationalFlags
        exclude = ("user", "company", "created_at", "updated_at")
        widgets = {
            field: forms.CheckboxInput(attrs={"class": "form-check-input"})
            for field in [
                "is_operation_admin", "ignore_notification_emails",
                "is_seller_profile", "restricted_shop_access",
                "can_authorize_purchase_request", "can_close_purchase_order",
                "restrict_unaccepted_po_pdf", "can_close_sale_order",
                "see_all_price_lists", "can_close_credits",
            ]
        }


class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = ("name", "description")
        widgets = {
            "name": forms.TextInput(attrs={"autofocus": True}),
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        qs = Role.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe un rol con este nombre.")
        return name


class PermissionForm(forms.ModelForm):
    class Meta:
        model = Permission
        fields = ("code", "action_name", "module", "description")


class CompanyAdminForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ("name", "ruc", "address", "email", "phone", "is_active")
        widgets = {
            "name": forms.TextInput(attrs={"autofocus": True}),
            "address": forms.TextInput(),
        }

    def clean_ruc(self):
        ruc = self.cleaned_data["ruc"].strip()
        qs = Company.objects.filter(ruc=ruc)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe una empresa con este RUC.")
        return ruc


class CompanyBrandingAdminForm(forms.ModelForm):
    class Meta:
        model = CompanyBranding
        fields = ("app_logo_url", "primary_color", "secondary_color")
        widgets = {
            "primary_color": forms.TextInput(attrs={"type": "color", "class": "form-control form-control-color"}),
            "secondary_color": forms.TextInput(attrs={"type": "color", "class": "form-control form-control-color"}),
            "app_logo_url": forms.URLInput(attrs={"placeholder": "https://...  (URL del logo)"}),
        }
        labels = {
            "app_logo_url": "URL del logo",
            "primary_color": "Color primario",
            "secondary_color": "Color secundario",
        }


class StoreAdminForm(forms.ModelForm):
    class Meta:
        model = Store
        fields = ("name", "address", "active", "lock_movement_edits")
        widgets = {
            "name": forms.TextInput(attrs={"autofocus": True}),
        }
