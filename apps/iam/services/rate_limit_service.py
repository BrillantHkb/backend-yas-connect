"""Rate-limit login (AUTH-06) : compteurs cache identifiant + IP. Redis si REDIS_URL."""

from django.conf import settings
from django.core.cache import cache


def _ident_key(ident: str) -> str:
    """Clé cache : email ou username (lower) pour ne pas doubler jean / Jean."""
    value = ident.strip().lower()
    kind = "email" if "@" in value else "username"
    return f"login:attempts:{kind}:{value}"


def _ip_key(ip: str) -> str:
    """Clé cache par IP (limite NAT partagée : on ne reset pas l’IP après succès)."""
    return f"login:attempts:ip:{ip}"


def is_limited(ident: str) -> bool:
    """True si ≥ 5 tentatives sur cet identifiant dans la fenêtre (défaut 15 min)."""
    current = cache.get(_ident_key(ident), 0)
    return current >= settings.LOGIN_RATE_LIMIT_ATTEMPTS


def is_limited_ip(ip: str | None) -> bool:
    """True si ≥ 20 tentatives sur cette IP. Ignoré si IP inconnue."""
    if not ip:
        return False
    current = cache.get(_ip_key(ip), 0)
    return current >= settings.LOGIN_RATE_LIMIT_IP_ATTEMPTS


def hit(ident: str, ip: str | None) -> None:
    """Incrémente identifiant et IP à chaque tentative (succès ou échec)."""
    window = settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS
    ident_cache = _ident_key(ident)
    cache.add(ident_cache, 0, window)  # crée la clé avec TTL si absente
    try:
        cache.incr(ident_cache)
    except ValueError:  # backend sans incr fiable
        cache.set(ident_cache, 1, window)
    if ip:
        ip_cache = _ip_key(ip)
        cache.add(ip_cache, 0, window)
        try:
            cache.incr(ip_cache)
        except ValueError:
            cache.set(ip_cache, 1, window)


def reset(ident: str) -> None:
    """Après login OK : on remet l’identifiant à zéro. Pas l’IP (NAT)."""
    cache.delete(_ident_key(ident))


def _mfa_user_key(user_id) -> str:
    """Compteur OTP / backup faux, distinct du login MDP."""
    return f"mfa:attempts:user:{user_id}"


def _mfa_ip_key(ip: str) -> str:
    return f"mfa:attempts:ip:{ip}"


def is_mfa_limited(user_id) -> bool:
    """True si trop d’OTP / backup faux (AUTH-C)."""
    current = cache.get(_mfa_user_key(user_id), 0)
    return current >= settings.YAS_MFA_OTP_ATTEMPTS


def is_mfa_limited_ip(ip: str | None) -> bool:
    """Même plafond que l’user (YAS_MFA_OTP_ATTEMPTS). Ignoré si IP inconnue."""
    if not ip:
        return False
    current = cache.get(_mfa_ip_key(ip), 0)
    return current >= settings.YAS_MFA_OTP_ATTEMPTS


def mfa_hit(user_id, ip: str | None) -> None:
    """Incrémente user + IP à chaque verify (succès ou échec, avant le check TOTP)."""
    window = settings.YAS_MFA_OTP_WINDOW_SECONDS
    user_cache = _mfa_user_key(user_id)
    cache.add(user_cache, 0, window)
    try:
        cache.incr(user_cache)
    except ValueError:
        cache.set(user_cache, 1, window)
    if ip:
        ip_cache = _mfa_ip_key(ip)
        cache.add(ip_cache, 0, window)
        try:
            cache.incr(ip_cache)
        except ValueError:
            cache.set(ip_cache, 1, window)


def mfa_reset(user_id) -> None:
    """Succès OTP : on oublie les échecs de cet user."""
    cache.delete(_mfa_user_key(user_id))
