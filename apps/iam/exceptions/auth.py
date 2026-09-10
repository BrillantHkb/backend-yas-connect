"""Exceptions métier IAM. Le handler core formate {success, code, message}."""


class AuthAPIError(Exception):
    """Erreur auth renvoyée au client sous {success, code, message} (+ extra)."""

    def __init__(self, status_code: int, code: str, message: str, extra=None):
        self.status_code = status_code  # 400 / 401 / 403 / 409 / 410 / 429 / 503
        self.code = code
        self.message = message
        self.extra = extra or {}  # FORBIDDEN.permission, ROLE_IN_USE.users_count, …
        super().__init__(message)
