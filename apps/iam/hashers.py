"""Argon2id YAS (AUTH-A §2) + dummy hash anti-énumération (AUTH-05)."""

from django.contrib.auth.hashers import Argon2PasswordHasher, check_password

_DUMMY_HASH: str | None = None  # calculé une fois, réutilisé (Argon2 est coûteux)


class YasArgon2PasswordHasher(Argon2PasswordHasher):
    """Hasher de production : plus strict que le défaut Django (t=2)."""

    time_cost = 3  # itérations (t)
    memory_cost = 65536  # KiB (m=65536)
    parallelism = 1  # threads (p=1)


def dummy_hash() -> str:
    """Hash Argon2id figé : égalise le temps de réponse si l’email/username n’existe pas."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:  # lazy : pas de coût au import / migrate
        hasher = YasArgon2PasswordHasher()
        _DUMMY_HASH = hasher.encode("not-the-password", hasher.salt())  # jamais un vrai MDP
    return _DUMMY_HASH


def verify_dummy(password: str) -> bool:
    """Compare le MDP tenté au dummy (timing AUTH-05). Le booléen n’est pas lu au login."""
    return check_password(password, dummy_hash())
