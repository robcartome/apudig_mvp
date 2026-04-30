"""
users/selectors.py — Consultas de lectura de usuarios.
"""
from django.contrib.auth import get_user_model

User = get_user_model()


def get_active_users():
    return User.objects.filter(is_active=True).order_by("email")


def get_user_by_email(email: str):
    return User.objects.filter(email__iexact=email).first()
