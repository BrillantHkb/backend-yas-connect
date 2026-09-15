"""AUTH-I : alertes stub restantes. DEVICE_NEW remplacé par notifications.emit() (NOTIF-A)."""

import logging

logger = logging.getLogger(__name__)


def notify_suspicious_login(*, user, history, previous_country: str) -> None:
    """AUTH-62 : log seulement. NOTIF-A poussera l’alerte réel."""
    logger.info(
        "LOGIN_NEW_COUNTRY user=%s history=%s from=%s to=%s",
        user.id,
        history.id,
        previous_country,
        history.country,
    )


def notify_email_verification(*, user, email: str, purpose: str) -> None:
    """AUTH-65/66 : log le lien (pas le token). SMTP réel = EMAIL_HOST si configuré."""
    logger.info(
        "EMAIL_VERIFICATION user=%s email=%s purpose=%s",
        user.id,
        email,
        purpose,
    )
