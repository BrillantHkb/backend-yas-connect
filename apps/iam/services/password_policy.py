"""Politique MDP applicatif AUTH-D / AUTH-G. Défauts contractuels + system_settings."""

from django.conf import settings

from apps.iam.exceptions import AuthAPIError

SPECIAL = set("!@#$%^&*()_+-={}[]:;,.?")  # jeu contractuel AUTH-D
MSG_WEAK = "Mot de passe trop faible."


def _security_value(key: str, default):
    """Lit security.* si la ligne existe, sinon défaut (.env / AUTH-D)."""
    from apps.config.models import SystemSetting  # import tardif : éviter cycle apps

    row = SystemSetting.objects.filter(category="security", setting_key=key).first()
    if row is None or row.setting_value is None:
        return default
    return row.setting_value


def password_history_n() -> int:
    """N hashes à comparer (AUTH-45). DB prioritaire, sinon .env."""
    raw = _security_value("password_history_n", None)
    if raw is None:
        return settings.YAS_PASSWORD_HISTORY_N
    return int(raw)


def password_reset_ttl() -> int:
    """TTL du ticket après TOTP OK (secondes)."""
    raw = _security_value("password_reset_ttl_seconds", None)
    if raw is None:
        return settings.YAS_PASSWORD_RESET_TTL_SECONDS
    return int(raw)


def _as_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("1", "true", "yes")


def enforce_password_policy(password: str, *, email: str = "", username: str = "") -> None:
    """400 WEAK_PASSWORD si hors politique. Ne jamais logger le clair."""
    min_len = int(_security_value("password_min_length", 10))
    max_len = int(_security_value("password_max_length", 128))
    if len(password) < min_len or len(password) > max_len:
        raise AuthAPIError(400, "WEAK_PASSWORD", MSG_WEAK)
    if _as_bool(_security_value("password_require_upper", True), True) and not any(
        c.isupper() for c in password
    ):
        raise AuthAPIError(400, "WEAK_PASSWORD", MSG_WEAK)
    if _as_bool(_security_value("password_require_lower", True), True) and not any(
        c.islower() for c in password
    ):
        raise AuthAPIError(400, "WEAK_PASSWORD", MSG_WEAK)
    if _as_bool(_security_value("password_require_digit", True), True) and not any(
        c.isdigit() for c in password
    ):
        raise AuthAPIError(400, "WEAK_PASSWORD", MSG_WEAK)
    if _as_bool(_security_value("password_require_special", True), True) and not any(
        c in SPECIAL for c in password
    ):
        raise AuthAPIError(400, "WEAK_PASSWORD", MSG_WEAK)
    lowered = password.lower()
    # Interdit d’égaler l’identifiant (même en changeant la casse)
    if email and lowered == email.strip().lower():
        raise AuthAPIError(400, "WEAK_PASSWORD", MSG_WEAK)
    if username and lowered == username.strip().lower():
        raise AuthAPIError(400, "WEAK_PASSWORD", MSG_WEAK)
