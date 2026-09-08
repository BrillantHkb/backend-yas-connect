"""Politique MDP applicatif AUTH-D (D02/D03). Défauts contractuels."""

from apps.iam.exceptions import AuthAPIError

SPECIAL = set("!@#$%^&*()_+-={}[]:;,.?")  # jeu contractuel AUTH-D
MSG_WEAK = "Mot de passe trop faible."


def enforce_password_policy(password: str, *, email: str = "", username: str = "") -> None:
    """400 WEAK_PASSWORD si hors politique. Ne jamais logger le clair."""
    if len(password) < 10 or len(password) > 128:
        raise AuthAPIError(400, "WEAK_PASSWORD", MSG_WEAK)
    if not any(c.isupper() for c in password):
        raise AuthAPIError(400, "WEAK_PASSWORD", MSG_WEAK)
    if not any(c.islower() for c in password):
        raise AuthAPIError(400, "WEAK_PASSWORD", MSG_WEAK)
    if not any(c.isdigit() for c in password):
        raise AuthAPIError(400, "WEAK_PASSWORD", MSG_WEAK)
    if not any(c in SPECIAL for c in password):
        raise AuthAPIError(400, "WEAK_PASSWORD", MSG_WEAK)
    lowered = password.lower()
    # Interdit d’égaler l’identifiant (même en changeant la casse)
    if email and lowered == email.strip().lower():
        raise AuthAPIError(400, "WEAK_PASSWORD", MSG_WEAK)
    if username and lowered == username.strip().lower():
        raise AuthAPIError(400, "WEAK_PASSWORD", MSG_WEAK)
