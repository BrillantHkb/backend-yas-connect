"""AUTH-59 : blacklist JTI access jusqu’à exp JWT. Redis down → ignorer (session DB = vérité)."""

from django.conf import settings
from django.core.cache import cache


def _key(jti) -> str:
    return f"jti:{jti}"


def blacklist_jti(jti, ttl=None) -> None:
    """Pose jti:{uuid} jusqu’à TTL (secondes). Exception cache → no-op, pas de 503."""
    if jti is None:
        return
    timeout = int(ttl if ttl is not None else settings.YAS_JWT_ACCESS_TTL_SECONDS)
    if timeout < 1:
        timeout = 1
    try:
        cache.set(_key(jti), 1, timeout=timeout)
    except Exception:
        return


def jti_blocked(jti) -> bool:
    """True si le JTI est en cache. Cache down → False (on s’en remet à la session)."""
    if jti is None:
        return False
    try:
        return bool(cache.get(_key(jti)))
    except Exception:
        return False
