"""Exceptions métier IAM (AUTH-A). Pas une APIException DRF : le handler core les formate."""


class AuthAPIError(Exception):
    """Erreur auth renvoyée au client sous {success, code, message}."""

    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code  # 401 ou 403 (jamais 429 : pas d’énumération throttle)
        self.code = code  # ex. INVALID_CREDENTIALS, ACCOUNT_LOCKED
        self.message = message  # texte UI, unique pour les 401 login
        super().__init__(message)  # pour les logs / traceback
