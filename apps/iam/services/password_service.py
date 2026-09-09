"""Vérification mot de passe réel (AUTH-01) vs dummy (AUTH-05)."""

from django.contrib.auth.hashers import check_password

from apps.iam.helpers.hashers import verify_dummy  # réexport : auth_service n’importe pas hashers

__all__ = ["verify_dummy", "verify_password"]


def verify_password(password: str, encoded: str) -> bool:
    """True si le clair correspond au hash stocké (users.password_hash / colonne password)."""
    return check_password(password, encoded)
